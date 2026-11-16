# Smart Hotel Monitoring System - opencode.md

Canonical end-to-end project reference and working memory for this repository.
Read this file before making changes. Update this file after every change (see
[Conventions and Change Guide](#11-conventions-and-change-guide)). If this file
and the code disagree, the code wins; fix this file as part of the change.

Last verified: 2026-11-15, working tree after complete security audit & hardening,
AlertRateLimiter/NotificationHub integration, and the Approach B cloud architecture
implementation (Vercel Serverless + Supabase PostgreSQL & Storage + Node.js/Express
Central Server rewrite + 3s HTTP Edge Poller). Python 3.11/3.14, Node 22.20.0, npm 11.6.0,
Windows 10/11 + PowerShell 5.1. The edge repo has `requirements.txt` and `.gitignore`
protecting database/env files. The sibling central server (`D:\Projects\SHMS_central_server`)
now has full Vercel deployment configuration (`vercel.json`), root `package.json`,
Supabase PostgreSQL schema (`supabase_schema.sql`), and a clean Node.js/Express serverless
backend (`api/index.js`, `lib/supabase.js`, `lib/auth.js`, `lib/db.js`, `server.js`).

---

## 1. What This Project Is

An AI CCTV surveillance and compliance dashboard for hotel/commercial kitchens.
It ingests RTSP/HTTP/USB/video-file streams, runs YOLOv8 inference per camera,
applies two-tier geometric and temporal filtering (AMFV), stores violations in SQLite,
captures forensic HUD-watermarked evidence snapshots, and alerts via Gmail SMTP,
multi-platform webhooks (Slack/Discord/Telegram), and cloud fleet synchronization
(Approach B: 3-second HTTP command polling + direct Supabase Storage upload).

The system spans two sibling project folders (three runnable services):

1. **Main surveillance app** - FastAPI on port 8000 + React 19 dashboard
   (this repository: `D:\Projects\Smart-hotel-monitoring-system`).
2. **Mobile stream relay** - standalone FastAPI on port 8080 that turns a phone
   browser camera into an MJPEG URL consumable by the main app (subfolder here).
3. **Central fleet/admin server** - Node.js/Express serverless backend on port 9000
   (or Vercel HTTPS) + React 19 fleet portal at `D:\Projects\SHMS_central_server`.
   Backed by PostgreSQL and Storage in Supabase. It receives edge pairing/polls/incidents,
   provides the master admin portal, stores evidence in Supabase Storage buckets, and
   manages fleet commands (live snapshot inspection, remote AMFV configuration).
   It is fully **Vercel-ready** via `vercel.json` (see sections 3.1, 4.7, 6, and 10).

The YOLO model (`best.pt`) actually contains **9 classes**:
`apron`, `cockroach`, `gloves`, `hairnet`, `lizard`, `no_apron`, `no_gloves`,
`no_hairnet`, `rat`. The app only reacts to 6 violation labels:

| Group | Labels | Color in UI |
| :--- | :--- | :--- |
| Pests | `cockroach`, `lizard`, `rat` | Rose/crimson |
| Hygiene/PPE | `no_apron`, `no_gloves`, `no_hairnet` | Amber |

`apron`, `gloves`, and `hairnet` (positive PPE detections) are intentionally
ignored by `camera_manager.VIOLATIONS`.

---

## 2. Runtime Architecture

```text
Browser (React 19 + Vite/Tailwind/shadcn)
   |  polling: /cameras /logs /stats /amfv_status /system_info /analytics ...
   |  MJPEG images: <img src="/video_feed/{camera_id}">
   v
FastAPI main app :8000  (main.py)
   |-- CameraManager -> one daemon CameraStream thread per enabled camera
   |      |-- cv2.VideoCapture(RTSP/HTTP/webcam/file) with scheme validation
   |      |-- YOLO best.pt inference (serialized by a global lock)
   |      |-- Tier 1 Confidence Calibration + Tier 2 Geometric Noise Filter (aspect > 7, size < 12px)
   |      |-- AMFV rolling windows (dynamic window size) + cooldown
   |      `-- on_violation callback -> watermark -> local SQLite
   |-- Database -> SQLite hotel_monitoring.db (WAL, thread-local, credential masking)
   |-- snapshots/*.jpg served at /snapshots (relative URLs)
   |-- NotificationHub -> Anti-spam AlertRateLimiter + responsive HTML email (CID image) + Webhooks
   `-- EdgeSyncManager (daemon supervisor, Approach B)
          |  POST /api/edge/pair (enrollment & auto-provisioning)
          |  POST /api/edge/poll (3-second HTTP poll: heartbeats + claims pending commands)
          |  POST /api/edge/command_reply (delivers ephemeral base64 live snapshots)
          |  PUT/POST /storage/v1/object/evidence-snapshots/... (direct Supabase upload)
          `-- POST /api/edge/batch_sync (hourly metadata upload < 30KB; bypasses Vercel 4.5MB cap)
          v
Central fleet server :9000 / Vercel Serverless (D:\Projects\SHMS_central_server)
   |-- Node.js / Express Serverless (api/index.js, lib/supabase.js, lib/db.js)
   |-- Supabase PostgreSQL: owners, edge_nodes, fleet_violations, edge_commands, admin_users
   |-- Supabase Storage: "evidence-snapshots" bucket (permanent violation CDN URLs)
   |-- Command Queue: on-demand live snapshot requests & remote calibration
   `-- Admin Auth / Sessions via JWT HttpOnly cookie
          ^
Central admin browser -> React 19 fleet portal :9000/admin (Vercel CDN)

Phone browser -> mobile_stream_server/server.py :8080
   WebSocket /ws/stream (JPEG binaries, 5MB cap) -> /video MJPEG relay
   The main app consumes that URL as source_type="http".
```

Key implications:

- Inference is per-frame, no frame skipping, and serialized across all cameras by
  `_MODEL_INFERENCE_LOCK` in `camera_manager.py`. More cameras means lower effective
  FPS per camera.
- `fps` reported by the app is inference throughput (1 / average processing time),
  not source FPS.
- Video-file sources loop forever via `CAP_PROP_POS_FRAMES = 0`.
- RTSP/HTTP/webcam sources reconnect with exponential backoff, capped at 30s.
- `video_feed` is MJPEG (multipart/x-mixed-replace) of the **annotated** frames.

---

## 3. Repository Map

### Root

| Path | Purpose |
| :--- | :--- |
| `main.py` | FastAPI app, all HTTP/streaming/export endpoints, alert dispatch, startup/shutdown. |
| `camera_manager.py` | `CameraStream`, `CameraManager`, YOLO inference, AMFV, reconnect, MJPEG generator. |
| `database.py` | SQLite persistence: cameras, violations, settings, stats, analytics. |
| `edge_sync.py` | `EdgeSyncManager`: duplex registration, WebSocket commands, heartbeat, snapshot replies, and idempotent hourly/on-demand batch sync. |
| `requirements.txt` | Python runtime dependencies, including `websocket-client` for the duplex channel. |
| `train_finetune.py` | YOLOv8 fine-tuning pipeline (local data.yaml or Roboflow download). |
| `best.pt` | Active YOLOv8 PyTorch weights (9 classes). Loaded as `YOLO("best.pt")`. |
| `best.onnx` | ONNX export; not referenced by runtime code. |
| `hotel_monitoring.db` (+ `-shm`, `-wal`) | Committed SQLite database and WAL sidecars. |
| `demo.mp4`, `demo1.mp4`, `demo3.mp4`, `demo4.mp4` | Test videos. `demo1.mp4` is the auto-seed default. |
| `snapshots/` | Runtime evidence JPEGs; served at `/snapshots`; git-ignored. |
| `utils/watermark.py` | Forensic HUD watermark + SHA-256 frame fingerprint for evidence snapshots. |
| `utils/alert_dispatcher.py` | Standalone anti-spam notification hub: cooldown rate limiter, branded HTML email builder, and Slack/Discord/Telegram/generic webhook adapters. Not yet wired into `main.py` (see section 4.8). |
| `utils/test_watermark.jpg` | Generated watermark verification artifact. |
| `templates/index.html` | Stale built React fallback used only if `frontend/dist/index.html` is missing. |
| `README.md` | Product/marketing documentation. Contains claims not implemented by code; see section 11. |
| `mobile_stream_server/` | Standalone phone-camera relay app (port 8080). |

### Frontend (`frontend/`)

| Path | Purpose |
| :--- | :--- |
| `package.json` | React 19, Vite 8, Tailwind 3, Radix/shadcn, Chart.js, Lucide. Scripts: `dev`, `build`, `lint`, `preview`. |
| `vite.config.js` | Dev server port 3000, proxies backend paths to `http://127.0.0.1:8000`. |
| `tailwind.config.js` | shadcn HSL token mapping; Plus Jakarta Sans / JetBrains Mono. |
| `src/main.jsx` | React root bootstrap. |
| `src/App.jsx` | Top-level state, polling, layout, modal orchestration, zoom overlay. |
| `src/services/api.js` | Single REST client; `BASE_URL = ''` (relative URLs). |
| `src/index.css` | Dark ash-grey design tokens, scrollbars, pulse keyframes. |
| `src/components/Navbar.jsx` | Brand, live clock, camera count, Add Camera/Analytics/Evidence/CSV/Settings actions, central connection status/button. |
| `src/components/CentralConnectModal.jsx` | Central URL + hotel/kitchen/location form; calls `/api/central/connect`. |
| `src/components/KpiStrip.jsx` | Compact totals (total/pest/hygiene/AMFV state) + focus reset + inspector collapse. |
| `src/components/CameraGrid.jsx` | Camera cards, 16:9 MJPEG stage, focus mode, per-camera dropdown. |
| `src/components/InspectorDock.jsx` | 3-tab rail: Logs, AMFV telemetry, Cameras. |
| `src/components/AddCameraModal.jsx` | RTSP/HTTP/webcam/file wizard, brand presets, connection test. |
| `src/components/SettingsModal.jsx` | Detection/AMFV/alert settings form. |
| `src/components/AnalyticsModal.jsx` | Chart.js daily trend, hourly bars, per-camera breakdown. |
| `src/components/SnapshotGalleryModal.jsx` | Evidence gallery, filters, review acknowledgement. |
| `src/components/ui/*.jsx` | shadcn/Radix primitives: badge, button, card, dialog, dropdown-menu, input, label, progress, separator, slider, switch, tabs. |
| `frontend/dist/` | Production build served by FastAPI (git-ignored). |
| `frontend/public/` | `favicon.svg`, `icons.svg`. |

### Mobile relay (`mobile_stream_server/`)

| Path | Purpose |
| :--- | :--- |
| `server.py` | FastAPI on 8080: phone capture page, WebSocket receiver, MJPEG relay. |
| `templates/index.html` | Laptop dashboard with QR code / preview. |
| `templates/camera.html` | Phone camera capture UI (getUserMedia, flip, resolution, torch). |
| `README.md` | Setup + mobile-browser HTTPS/permission troubleshooting. |

### 3.1 Central Fleet Server (`D:\Projects\SHMS_central_server`)

Separate sibling folder outside this git repository. It is the admin/control
plane for one or many edge installations. It has been redesigned and rewritten as a
**native Node.js / Express Serverless application on Vercel backed by PostgreSQL & Storage in Supabase**
(Approach B).

| Path | Purpose |
| :--- | :--- |
| `package.json` | Root Node.js project: `@supabase/supabase-js`, `express`, `bcryptjs`, `jsonwebtoken`, `cookie-parser`, `cors`, `dotenv`. Scripts: `dev`, `start`, `build`. |
| `vercel.json` | Vercel production deployment config: builds `frontend/dist` and routes `/api/*` to `api/index.js` with SPA fallback. |
| `supabase_schema.sql` | Production PostgreSQL DDL: `owners`, `pairing_codes`, `edge_nodes`, `fleet_violations`, `edge_commands`, `admin_users`, `central_settings`, `audit_logs`, indexes, and Storage bucket policies. |
| `api/index.js` | Express serverless router: Auth, Fleet APIs, Command Queue, 3s Edge Polling (`/api/edge/poll`), Snapshot Reply (`/api/edge/command_reply`), Batch Ingestion (`/api/edge/batch_sync`). |
| `lib/supabase.js` | Supabase service client (`createClient`) bypassing RLS for server-side management. |
| `lib/auth.js` | JWT session cookies (`createSessionToken`, `verifySessionToken`), bcrypt hashing, HMAC-SHA256 edge token verification (`hashEdgeToken`). |
| `lib/db.js` | Supabase repository layer: fleet nodes, command queues, batch violation upserts, analytics aggregation, pairing codes. |
| `server.js` | Local development runner on port 9000: serves static React `frontend/dist` and mounts Express API. |
| `.env.example` | Template for `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_BUCKET`, `SHMS_SECRET_KEY`, `PORT`. |
| `frontend/` | React 19 + Vite 8 fleet portal (login, KPI strip, node cards, live snapshot modal, remote config modal, evidence vault, analytics, settings). |
| `frontend/dist/` | Production build served statically by Vercel CDN and `server.js`. |
| `server.py`, `database.py`, etc. | Legacy Python FastAPI + SQLite implementation preserved for local testing/reference. |

Runtime defaults: `PORT=9000` (locally) or Vercel managed HTTPS; secret `shms-enterprise-central-secret-key-2026-v1`;
session cookie `shms_central_session` (24h); default admin `admin` / `admin123`.
All overridable via `.env` or Vercel Environment Variables. Default owner: `OWN-DEFAULT-SYSTEM`.

---

## 4. Backend Deep Dive

### 4.1 `main.py`

Initialization order:

1. Register MIME types for `.js`/`.css`/`.svg` (Windows/Chrome fix).
2. Create FastAPI app and configured CORS with origin whitelist via `CORS_ORIGINS` (disallowing wildcard `*` with credentials).
3. Create `snapshots/` and mount `/snapshots`.
4. Mount `frontend/dist/assets` at `/assets`; create the dir if absent.
5. Open `Database("hotel_monitoring.db")` and load `YOLO("best.pt")`.
6. Warm up the model with a 320x320 black frame and print status.
7. Initialize `NotificationHub` (`utils.alert_dispatcher.py`) with environment-driven credentials (`SMTP_SENDER_EMAIL`, `SMTP_APP_PASSWORD`, `NOTIFICATION_EMAIL`) and rate limiter (`AlertRateLimiter`).
8. Create `CameraManager(model, on_violation)`.
9. Import and create `EdgeSyncManager(db, camera_manager)`.

Email and Alert Dispatching:

- Environment-driven: reads `SMTP_SENDER_EMAIL`, `SMTP_APP_PASSWORD`, `NOTIFICATION_EMAIL` (overridable via DB settings `notification_email`, `sender_email`, `app_password`). All hardcoded secrets removed.
- Responsive HTML alerts with inline `cid:evidence_snapshot` images, severity badges (rose for pest, amber for hygiene), and two-column KPI breakdown.
- Anti-spam rate limiting: `AlertRateLimiter` enforces a 60s cooldown per `camera_id:label` to eliminate inbox flooding during sustained detections.
- Toggle enforcement: `on_violation` strictly checks `email_alerts_enabled` and `webhook_alerts_enabled` before spawning daemon delivery threads.
- Multi-platform webhooks: auto-detects and formats payloads for Slack Block Kit, Discord embeds, Telegram MarkdownV2, or generic SHMS JSON.

`on_violation` callback sequence:

1. Build `snapshots/{camera_id}_{label}_{timestamp}.jpg` and write the annotated
   frame through `utils.watermark.save_watermarked_snapshot` (HUD metadata +
   SHA-256 fingerprint). Any watermark failure falls back to plain `cv2.imwrite`
   so evidence is still saved.
2. Insert violation row (`amfv_verified=1`, rounded ratio/confidence) with
   `synced_to_central=0`.
3. Look up camera name, log to terminal.
4. Dispatch alerts via `NotificationHub.dispatch_violation_alert` (checks toggles,
   applies rate limiting, spawns daemon workers). Central delivery is **not**
   immediate: `EdgeSyncManager` batches unsynced rows hourly or on demand.

Snapshot watermarking (`utils/watermark.py`):

- `save_watermarked_snapshot(frame, output_path, metadata)` applies a forensic
  HUD (hotel, location, camera, label/category, confidence, AMFV ratio,
  timestamp) plus a SHA-256 frame fingerprint, then writes with `cv2.imwrite`.
- `main.py` imports it lazily inside `on_violation`; missing module or any
  watermark exception falls back to an unwatermarked `cv2.imwrite`.
- The fingerprint is embedded in the image only; it is not stored in the
  `violations` table.

Startup/shutdown:

- `startup_event`: starts `EdgeSyncManager` (which resumes HTTP polling using persisted
  `central_url`/`kitchen_id`/`auth_token`), loads cameras from DB, and auto-seeds
  `cam_main` only when the DB has zero cameras. Seed source preference:
  `demo1.mp4` -> `demo.mp4` -> webcam `0`.
- Reads saved detection & calibration settings (`conf_threshold`, `imgsz`, `geometric_filter`,
  `enable_tta`, `iou_threshold`, `amfv_window`, `cooldown_seconds`) from DB and **applies them**
  to camera streams on startup.
- Each enabled saved camera is started through `camera_manager.add_camera`.
- `shutdown_event` stops all camera streams and calls `edge_sync.stop()`.

Camera & Snapshot API Sanitization:

- `/cameras` and `/cameras/{id}` sanitize camera records using `mask_url_credentials()`
  (masking passwords in RTSP/HTTP URLs) and strip raw plaintext `password` fields.
- `/snapshots_list` returns clean web-relative URLs `/snapshots/{filename}` instead
  of exposing absolute host filesystem paths.
- Fixed `cooldown_seconds == 0` falsy bug and dynamic AMFV window size reporting in `/amfv_status`.

Central-link endpoints added to `main.py`:

- `POST /api/central/connect` -> registers with central and opens the duplex
  channel; persists the returned kitchen ID/token.
- `GET /api/central/status` -> configured/connected flags, ledger counts, last
  sync result, and last error.
- `POST /api/central/sync_now` -> runs one batch sync synchronously.

Serving the UI:

- `GET /` prefers `frontend/dist/index.html`; otherwise Jinja2
  `templates/index.html`.
- Both paths add no-cache headers.
- `GET /favicon.svg` serves `frontend/dist/favicon.svg` if present.
- Static assets are mounted from `frontend/dist/assets`, so a production build
  must exist before starting the server for the real dashboard.

### 4.2 `camera_manager.py`

Constants (`camera_manager.py:18-22`):

| Constant | Actual value |
| :--- | :--- |
| `VIOLATIONS` | `cockroach, lizard, rat, no_apron, no_gloves, no_hairnet` |
| `PESTS` | `cockroach, lizard, rat` |
| `DEFAULT_AMFV_WINDOW` | `2` frames |
| `DEFAULT_AMFV_THRESHOLD_PEST` | `0.20` |
| `DEFAULT_AMFV_THRESHOLD_HYGIENE` | `0.40` |

`CameraStream` lifecycle:

- `_connect()` opens `cv2.VideoCapture`; RTSP buffersize is set to 1; verifies an
  initial frame read.
- HTTP sources with no path (or `/`) automatically get `/video` appended.
- `_reconnect()` uses delay `min(2 ** attempts, 30)` seconds.
- `_run()` reads frames, runs inference, updates `_latest_frame`/`_annotated_frame`
  under a lock, tracks FPS, increments `frame_count`, handles file looping and
  reconnects.
- `_process_frame()`:
  1. Runs `model(frame, verbose=False, conf=self.conf_threshold)` under the shared inference lock.
  2. Evaluates detections with **Tier 1 Confidence Calibration** (`conf >= conf_threshold`) and
     **Tier 2 Geometric Noise Filtering** (rejects detections with extreme aspect ratio `> 7.0` or
     tiny bounding box dimensions `< 12px`).
  3. Collects the max confidence per valid violation class present in the frame.
  4. For **every** violation class, appends 1/0 to a rolling deque
     (`amfv_window_size`), computes ratio = sum / len.
  5. If ratio >= threshold and class is not already confirmed: mark confirmed,
     then alert only if `now - last_alert >= cooldown_seconds` (default 30).
  6. If ratio < threshold: remove from confirmed.
  7. Callback signature: `(camera_id, label, timestamp, annotated_frame, ratio,
     confidence)`.
- `get_amfv_status()` returns current per-class ratios/confirmed/thresholds and
  dynamically reports live `window_size` (`self.amfv_window_size`).
- `reset_amfv()` clears windows, ratios, confirmed set, and cooldown timers.
- `generate_mjpeg()` yields JPEG boundary frames with ~30ms sleep while running.
- `stop()` joins the worker with a 5s timeout and releases the capture.

`CameraManager`:

- Holds a dict of camera_id -> CameraStream under a lock.
- `add_camera`, `remove_camera`, `get_camera`, `list_cameras`, `toggle_camera`,
  `stop_all`, `update_all_configs`.
- `test_connection(source, source_type)` validates URL protocol scheme (`rtsp`, `http`, `https`,
  file, webcam) to prevent SSRF, sets timeouts (4s), and returns
  `{success, resolution, preview(base64 JPEG), error}`.

### 4.3 `database.py`

SQLite with thread-local connections, `row_factory = sqlite3.Row`,
`PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
Includes credential sanitation helpers `mask_url_credentials` and `sanitize_camera_dict`
to strip plaintext passwords and mask embedded RTSP credentials (`rtsp://user:***@host`).

Schema:

```sql
cameras (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source TEXT NOT NULL,
  location TEXT DEFAULT '',
  source_type TEXT DEFAULT 'rtsp'
    CHECK(source_type IN ('rtsp','http','webcam','file')),
  enabled INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now')),
  username TEXT DEFAULT '',   -- plaintext
  password TEXT DEFAULT ''    -- plaintext
)

violations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  camera_id TEXT,             -- FK cameras(id) ON DELETE SET NULL
  label TEXT NOT NULL,
  timestamp TEXT NOT NULL,    -- "YYYY-MM-DD HH:MM:SS"
  amfv_verified INTEGER DEFAULT 0,
  amfv_ratio REAL DEFAULT 0.0,
  snapshot_path TEXT DEFAULT '',
  confidence REAL DEFAULT 0.0,
  acknowledged INTEGER DEFAULT 0,
  synced_to_central INTEGER DEFAULT 0,
  synced_at TIMESTAMP
)

settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)
```

Methods:

- Camera CRUD: `add_camera`, `get_camera`, `list_cameras`, `update_camera`,
  `delete_camera`.
- Violations: `add_violation`, `get_violations` (camera/label/limit/offset,
  ordered newest first), `get_violation_stats`, `clear_violations`,
  `acknowledge_violation`.
- Sync ledger: `get_unsynced_violations(limit=200)` (oldest first),
  `mark_violations_synced(ids)` (sets `synced_to_central=1` + `synced_at`),
  `get_sync_status()` (`total_count`, `synced_count`, `unsynced_count`,
  `last_synced_at`).
- Settings: `get_setting`, `set_setting`, `get_all_settings`.
- `get_violation_stats`: pests are hardcoded `cockroach/lizard/rat`;
  hygiene = total - pest; includes per-label breakdown.
- `get_analytics`: `daily` (up to 14 distinct days, ascending), `hourly`
  (always 24 `HH:00` keys), `by_camera` (ignores camera filter), `total`,
  `acknowledged`, `unacknowledged`.
- Tables are created with `CREATE TABLE IF NOT EXISTS`; there is no migration
  framework. `Database.__init__` runs a small idempotent migration that adds the
  sync-ledger columns to existing `violations` tables, so old databases keep
  working. Other schema changes still need explicit migration or DB recreation.

### 4.4 `edge_sync.py`

`EdgeSyncManager` is an HTTP-driven cloud synchronization supervisor (Approach B).
It reads persisted settings on startup (`central_url`, `kitchen_id`, `auth_token`,
`owner_id`, `pending_request_id`, `pending_pin`, `hotel_name`,
`kitchen_name`/`edge_name`, `edge_location`, `sync_interval_minutes`,
`supabase_url`, `supabase_anon_key`, `supabase_bucket`) and falls back to
`CENTRAL_SERVER_URL` (default `http://127.0.0.1:9000`).

- `connect_to_central(central_url, hotel_name, kitchen_name, location, owner_id, pairing_code)`
  POSTs `/api/edge/request_connection` (or `/api/edge/pair`) with tenant `owner_id`
  and optional pairing OTP. An approved response stores `kitchen_id`, `auth_token`,
  `supabase_url`, `supabase_anon_key`, and `supabase_bucket`, then starts the
  supervisor.
- A pending response returns immediately with `status="pending"`, `pin`, and
  `request_id`; a daemon thread polls `/api/edge/connection_status/<request_id>`
  every 3s, fetches `/api/edge/enrollment/<request_id>/credentials`, and applies
  the approved credentials.
- `start()` launches one daemon supervisor `_worker_loop` (Approach B):
  - Polls `POST /api/edge/poll` every 3 seconds with CPU/RAM telemetry, active camera
    states, and local unsynced count.
  - Central verifies the HMAC edge token and returns any pending commands.
  - Updates `_ws_connected = True` on successful poll responses so the local
    dashboard displays active cloud connectivity.
- Command Dispatcher:
  - `capture_snapshot` -> calls `_execute_snapshot_command`, captures frame from
    `camera_manager`, encodes to base64 JPEG, and calls `POST /api/edge/command_reply`.
    This delivers ephemeral live camera inspection directly to the central dashboard
    within ~3 seconds with **zero storage pileup** in Supabase!
  - `trigger_sync`/`sync_now` -> schedules an asynchronous batch sync.
  - `update_config` -> applies AMFV window/thresholds/cooldown to live streams and
    persists settings locally.
- Direct-to-Supabase Storage Batch Sync (`_run_batch_sync`):
  - Reads unsynced rows from local SQLite.
  - For each incident, `_upload_snapshot_to_supabase` pushes the JPEG directly to the
    Supabase Storage bucket (`evidence-snapshots/incidents/<filename>`) via HTTPS PUT/POST.
  - Replaces bulky base64 data with the permanent Supabase public CDN URL (`snapshot_url`).
  - Sends lightweight JSON metadata (< 30 KB) to `POST /api/edge/batch_sync`,
    **completely bypassing Vercel's 4.5 MB serverless request body limit**.
  - On central ACK (`synced_ids`), marks local SQLite rows synced via `mark_violations_synced`.
- The supervisor schedules a sync on connect if unsynced rows exist, and hourly after that.
  Failures are recorded in `last_error`/`last_sync_result` and never block local recording.

### 4.5 `train_finetune.py`

- Target classes: `["cockroach","lizard","rat","no_apron","no_gloves","no_hairnet"]`.
- `check_and_prepare_dataset` reads data.yaml, normalizes dict/list class names,
  warns if target classes are missing (catastrophic forgetting risk).
- Uses `subprocess.run(..., check=True)` instead of `os.system()` for secure, sanitized execution.
- Optional Roboflow download (`--rf-key --rf-workspace --rf-project --rf-version`).
- Trains from `best.pt` (falls back to `yolov8s.pt`), default 50 epochs,
  batch 16, imgsz 640, patience 15, optional `--device`, `--freeze`.
- Runs validation and prints precision/recall/mAP.
- `--deploy` backs up current `best.pt` to `best.pt.backup_<timestamp>` and
  copies the new best weights into place.

### 4.6 `mobile_stream_server/server.py`

- Standalone FastAPI app on `0.0.0.0:8080`.
- `GET /` laptop dashboard (QR code, stream URLs, preview).
- `GET /camera` phone camera capture page.
- `WS /ws/stream` receives binary JPEG frames from the phone, enforced with a **5 MB maximum frame cap** to prevent memory exhaustion DoS.
- `GET /video` and `/video_feed` MJPEG generator at ~30 FPS.
- Shows a generated standby frame when no fresh frame (<3.5s) is available.
- `GET /snapshot` single JPEG; `GET /status` connected/FPS/IP telemetry.

### 4.7 Central Fleet Server (`D:\Projects\SHMS_central_server`)

Purpose: aggregate all hotel edge installations into one admin portal, manage fleet
nodes, record verified evidence with permanent Supabase CDN URLs, and dispatch live
snapshot and remote AMFV calibration commands.

Architecture (Approach B - Vercel Serverless + Supabase):

- **Backend**: Express on Node.js 22 (`api/index.js`), completely compatible with
  Vercel Serverless Functions and local execution (`server.js`).
- **Database**: PostgreSQL on Supabase (`@supabase/supabase-js`), initialized via
  `supabase_schema.sql`.
- **Storage**: Supabase Storage bucket `evidence-snapshots` storing permanent violation JPEGs.
- **Frontend**: React 19 + Vite 8 SPA (`frontend/dist`), served directly by Vercel CDN
  with fallback routing in `vercel.json`.

PostgreSQL Schema (`supabase_schema.sql`):

```sql
owners (
  id TEXT PRIMARY KEY, company_name, contact_email, status, max_kitchens, created_at
)

pairing_codes (
  code TEXT PRIMARY KEY, owner_id REFERENCES owners, hotel_name, kitchen_name,
  created_by, created_at, expires_at, used BOOLEAN, used_by_edge_id, used_at
)

edge_nodes (
  id TEXT PRIMARY KEY, name, hotel_name, location, ip_address, api_url,
  status TEXT, auth_token TEXT, cameras_json JSONB, telemetry_json JSONB,
  config_json JSONB, last_heartbeat TIMESTAMPTZ, created_at TIMESTAMPTZ,
  owner_id REFERENCES owners, enrollment_status TEXT, request_id, pairing_pin,
  approved_by, approved_at, rejection_reason, last_hourly_sync, unsynced_count
)

edge_commands (
  id UUID PRIMARY KEY, edge_id REFERENCES edge_nodes, command TEXT, payload JSONB,
  status TEXT CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
  result_b64 TEXT, result_url TEXT, error_message TEXT, created_at, completed_at
)

fleet_violations (
  id BIGSERIAL PRIMARY KEY, edge_id REFERENCES edge_nodes, edge_name, hotel_name,
  camera_id, camera_name, label, category, timestamp TIMESTAMPTZ, confidence, amfv_ratio,
  snapshot_filename, snapshot_url TEXT, acknowledged BOOLEAN, reviewed_by, reviewed_at,
  local_violation_id INTEGER, owner_id REFERENCES owners
)

admin_users (id SERIAL PRIMARY KEY, username UNIQUE, password_hash, role, owner_id, is_superadmin)
central_settings (key PRIMARY KEY, value, updated_at)
audit_logs (id BIGSERIAL PRIMARY KEY, timestamp, actor, action, target_edge_id, details)
```

Command Queue & Polling Lifecycle:

1. **Live Snapshot**: Admin clicks "Take Snapshot" in the dashboard -> Central inserts
   `edge_commands(command='capture_snapshot', status='pending')` -> Edge polls `/api/edge/poll`
   within 3s -> Edge captures raw camera frame -> Edge calls `/api/edge/command_reply`
   with base64 JPEG -> Central completes command -> Admin sees snapshot in UI (~3s turnaround).
   Snapshot is ephemeral in base64, leaving **zero storage footprint in Supabase Storage**.
2. **Batch Sync**: Edge uploads incident frames directly to Supabase Storage -> Edge posts
   metadata and public URLs to `/api/edge/batch_sync` -> Central upserts records into
   `fleet_violations` idempotently -> Returns `synced_ids` -> Edge marks records synced.
3. **Authentication**: Admin auth uses bcrypt password hashing and 24h JWT sessions stored
   in `HttpOnly SameSite=Lax` cookies (`shms_central_session`). Edge tokens use HMAC-SHA256
   verification against `SHMS_SECRET_KEY`.

### 4.8 Alert Dispatcher (`utils/alert_dispatcher.py`)

Pure standard-library notification module (`smtplib`, `email.mime`, `urllib.request`,
`threading`, `time`, `json`). **Now fully integrated into `main.py`** via `on_violation`.

- `AlertRateLimiter(default_cooldown_seconds=60)`: Thread-safe in-memory rate limiter keyed
  on `"{camera_id}:{violation_label}"`. Prevents inbox spamming during prolonged violations.
- `build_html_alert_email(event_data, snapshot_path=None)`: Branded responsive HTML email with
  dark `#18181c` header, severity badges (rose `#dc2626` for pests, amber `#d97706` for hygiene),
  two-column KPI summary, and inline CID evidence snapshot (`<img src="cid:evidence_snapshot">`).
- `format_webhook_payload(event_data, platform="generic")`: Formats payloads for Slack Block Kit,
  Discord embeds, Telegram MarkdownV2, or generic SHMS JSON.
- `NotificationHub`: Asynchronously manages email and webhook delivery threads, enforcing
  `email_alerts_enabled` and `webhook_alerts_enabled` toggles.

---

## 5. Frontend Deep Dive

### 5.1 Stack and design

- React 19 (function components/hooks, no router), Vite 8, Tailwind CSS 3.
- shadcn-style primitives built on Radix UI; icons from Lucide; Chart.js for analytics.
- Dark "ash grey / crisp white" industrial theme defined in `src/index.css`
  (background `#0f0f12`, card `#18181c`, border `#29292e`; rose for pests,
  amber for hygiene, emerald for online/active).
- Fonts: Plus Jakarta Sans (sans), JetBrains Mono (mono).

### 5.2 `App.jsx` state and polling

State: `cameras`, `selectedCameraId`, `focusedCamId`, `stats`, `logs`,
`amfvData`, `systemInfo`, `isInspectorOpen`, modal booleans (including
`centralModalOpen`), `centralStatus`, `zoomedImageUrl`.

Polling:

- `fetchTelemetry` every **2200ms**: `Promise.allSettled` of `/logs`,
  `/amfv_status`, `/stats` (all filtered by `selectedCameraId`) and
  `/system_info`.
- `fetchCameras` every **6000ms**.
- `fetchCentralStatus` every **5000ms** (`/api/central/status`); drives the
  Navbar badge and sync/unsynced counts.
- No WebSocket/SSE to the browser; dashboard telemetry is polling. The edge
  process itself holds the WebSocket to central.
- Actions: add demo camera (`demo1.mp4`), remove camera (confirm), clear logs
  (confirm), CSV export via `window.open`.

Layout: `Navbar` -> `KpiStrip` -> grid of `CameraGrid` + `InspectorDock`
(collapsible, default open, right rail 370px) -> footer -> modals -> zoom dialog.

### 5.3 Component behavior notes

- `Navbar`: shows central connected/configured state, ledger unsynced count,
  opens `CentralConnectModal`, and triggers `sync_now`.
- `CentralConnectModal`: central URL, hotel, kitchen, location; posts
  `/api/central/connect` and refreshes status.
- `CameraGrid`: if no cameras, shows empty state with "Connect Camera" and
  "Load Demo Video". Video is `<img src="/video_feed/{id}">` with fallback to
  `/video_feed` on error. Focus mode hides other cards. Dropdown sets the global
  stats filter or removes the camera. Labels "YOLOv8 - Conf >= 45%" and
  "AMFV - W=10" are hardcoded cosmetic text, not live values.
- `InspectorDock`: three tabs.
  - Logs: all/pests/hygiene filter, CSV export, clear, snapshot thumbnails and
    zoom; map of labels to display titles.
  - AMFV: ratios vs thresholds with progress bars; threshold values come from
    the API; badge says window size from API.
  - Cameras: "All Cameras (Merged)" plus per-camera selection and status/FPS.
- `AddCameraModal`: source tabs RTSP/HTTP/webcam/file. RTSP presets:
  generic `/live`, mobile `/h264_pcm.sdp` port 8080, Hikvision
  `/Streaming/Channels/101`, Dahua `/cam/realmonitor?channel=1&subtype=0`,
  Reolink `/h264Preview_01_main`. HTTP auto-appends `/video` if the URL has no
  path. Test calls `/cameras/test`. Submit posts to `/cameras`.
- `SettingsModal`: loads `/settings`; sliders for confidence (20-90%),
  AMFV window (5-30), cooldown; inputs for imgsz/IoU/pest+hygiene thresholds,
  email, webhook. Saves many keys, but the backend only honors the subset listed
  in section 10. It does not expose `email_alerts_enabled`.
- `AnalyticsModal`: loads `/analytics`; Chart.js line (daily) and bar (hourly).
  It expects `data.summary` and `data.per_camera`, which the backend does not
  return (see section 11), so summary cards read 0 and the camera breakdown is
  empty.
- `SnapshotGalleryModal`: loads `/snapshots_list`, filters all/pest/hygiene,
  opens full-size image, posts `/violations/{id}/acknowledge`.

### 5.4 API client and dev proxy

- `src/services/api.js` uses relative URLs (`BASE_URL = ''`), so production works
  because FastAPI serves the SPA; dev works through Vite proxy.
- Vite proxies `/video_feed`, `/cameras`, `/logs`, `/stats`, `/amfv_status`,
  `/system_info`, `/settings`, `/analytics`, `/snapshots_list`, `/snapshots`,
  `/export`, `/clear_logs`, `/violations`, and `/api/central` to
  `127.0.0.1:8000`.
- `api.js` central helpers: `connectCentral`, `getCentralStatus`,
  `syncCentralNow`.
- `clearLogs` uses HTTP `DELETE /clear_logs` (README says POST; code/frontend use
  DELETE).
- `favicon.svg` is not in the proxy list, but the dev server serves
  `public/favicon.svg` itself.

---

## 6. HTTP API Reference (Main App, Port 8000)

| Method | Endpoint | Behavior / important params |
| :--- | :--- | :--- |
| GET | `/` | Serve `frontend/dist/index.html`, else `templates/index.html`. No-cache. |
| GET | `/favicon.svg` | Serve dist favicon or 404. |
| GET | `/cameras` | List DB cameras + live status, fps, frame_count, violation_count. |
| POST | `/cameras` | Body: `name` (required), `source_type`, and one of `source`/`url`/`device_index`/`file_path`; optional `location`, `username`, `password`. Creates `cam_<8 hex>` and starts worker. |
| GET | `/cameras/{id}` | Single camera with live status. |
| PUT | `/cameras/{id}` | Update DB fields; restarts stream if `source` or `source_type` changed. |
| DELETE | `/cameras/{id}` | Stop worker + delete DB row. |
| POST | `/cameras/{id}/toggle` | Flip enabled state and start/stop the worker. |
| POST | `/cameras/test` | Body: `source`, `source_type`. Returns `{success, resolution, preview(base64), error}`. |
| GET | `/video_feed/{camera_id}` | MJPEG stream for one camera (404 if not running). |
| GET | `/video_feed` | MJPEG from the first active camera (legacy). |
| GET | `/logs` | Query: `camera_id`, `label`, `limit=100`, `offset=0`. Formatted log objects incl. snapshot filename, AMFV/ack flags. |
| DELETE | `/clear_logs` | Query: optional `camera_id`. Deletes rows and resets AMFV state for affected streams. |
| POST | `/violations/{id}/acknowledge` | Set `acknowledged=1`. |
| GET | `/stats` | Query: optional `camera_id`. Returns `total`, `total_violations`, `pest`, `pest_detections`, `hygiene`, `hygiene_issues`, full 6-label `breakdown`. |
| GET | `/amfv_status` | Query: optional `camera_id`. Per-class `{ratio, threshold, confirmed}` plus `ratios`, `confirmed[]`, `thresholds`, `window_size`. |
| GET | `/system_info` | Model name, uptime, camera totals, frames processed, monitored labels. |
| GET | `/export/csv` | Query: optional `camera_id`. Streams CSV attachment (up to 5000 rows). |
| GET | `/analytics` | Query: optional `camera_id`. Returns `daily`, `hourly`, `by_camera`, `total`, `acknowledged`, `unacknowledged`. |
| GET | `/snapshots_list` | Query: `camera_id`, `label`, `limit=60`. Evidence gallery items with resolved URLs. |
| GET | `/settings` | Returns `amfv_window`, `amfv_threshold_pest`, `amfv_threshold_hygiene`, `cooldown_seconds`, `notification_email`, `webhook_url`, `email_alerts_enabled`. |
| POST | `/settings` | Persists and live-applies only `amfv_window`, `amfv_threshold_pest`, `amfv_threshold_hygiene`, `cooldown_seconds`, `notification_email`, `webhook_url`, `email_alerts_enabled`. Other keys are ignored. |
| GET | `/snapshots/{filename}` | Static mount of the `snapshots/` directory. |
| POST | `/api/central/connect` | Body: `central_url`, `hotel_name`, `kitchen_name`, optional `location`. Registers, persists credentials, opens duplex channel. |
| GET | `/api/central/status` | Configured/connected flags, kitchen ID, interval, ledger counts, last sync/error. |
| POST | `/api/central/sync_now` | Runs one synchronous batch sync and returns its result. |

### Mobile relay API (Port 8080)

| Method | Endpoint | Behavior |
| :--- | :--- | :--- |
| GET | `/` | Laptop dashboard / QR code. |
| GET | `/camera` | Phone capture UI. |
| WS | `/ws/stream` | Receive binary JPEG frames from phone. |
| GET | `/video`, `/video_feed` | MJPEG relay (standby frame if stale). |
| GET | `/snapshot` | Current JPEG or standby frame. |
| GET | `/status` | `{connected, phones_connected, fps, local_ip, port}`. |

### Central Fleet Server API (Port 9000 / Vercel Serverless, Node.js + Supabase)

Edge Appliance Ingestion & Command Protocol (Approach B):

| Method | Endpoint | Behavior |
| :--- | :--- | :--- |
| POST | `/api/edge/pair` | One-touch enrollment handshake: registers edge node, validates optional pairing OTP, creates `edge_nodes` record, and returns `auth_token` + Supabase Storage upload configuration (`supabase_url`, `supabase_anon_key`, `supabase_bucket`). |
| POST | `/api/edge/request_connection` | Alias for `/api/edge/pair` supporting backward-compatible registration payloads. |
| GET | `/api/edge/connection_status/{request_id}` | Pending enrollment status check: returns status (`pending`, `approved`, `rejected`), kitchen ID, and owner. |
| GET | `/api/edge/enrollment/{request_id}/credentials` | Obtains approved node `auth_token` and Supabase configuration once manager approves. |
| POST | `/api/edge/poll` | **Core 3s HTTP Polling loop**: edge pushes telemetry (`cpu`, `ram`, `disk`), active camera states, and unsynced count; server verifies HMAC token and returns queued `edge_commands` (`capture_snapshot`, `update_config`, `trigger_sync`). |
| POST | `/api/edge/command_reply` | Edge posts execution result for a command. For `capture_snapshot`, edge delivers base64 JPEG directly to resolve the live snapshot request with **zero storage pileup** in Supabase Storage. |
| POST | `/api/edge/batch_sync` | Token-authenticated batch sync: receives incident array with permanent Supabase Storage public CDN URLs (`snapshot_url`), upserts records into `fleet_violations` idempotently, and returns `synced_ids` (< 30 KB payload, bypassing Vercel's 4.5 MB cap). |
| POST | `/api/edge/heartbeat` | Backward-compatibility alias for `/api/edge/poll`. |

Admin Authentication & Fleet Management (Vercel Serverless):

| Method | Endpoint | Behavior |
| :--- | :--- | :--- |
| POST | `/api/auth/login` | Body `username`, `password`; verifies against Supabase `admin_users` with bcrypt; sets HttpOnly 24h JWT session cookie. |
| POST | `/api/auth/logout` | Clears session cookie. |
| GET | `/api/auth/me` | Returns authenticated user profile and tenant owner ID from JWT. |
| GET | `/api/fleet/overview` | Aggregated fleet KPIs: total nodes, online nodes, today's violations, pending alerts. |
| GET | `/api/fleet/owner_info` | Owner profile and kitchen capacity. |
| GET | `/api/fleet/enrollment/pending` | Lists pending edge nodes awaiting admin approval. |
| POST | `/api/fleet/enrollment/{request_id}/approve` | Approves pending node, generates edge auth token, sets status approved. |
| POST | `/api/fleet/enrollment/{request_id}/reject` | Rejects pending node with optional rejection reason. |
| POST | `/api/fleet/pairing_codes` | Generates a 6-character pairing PIN for fast edge enrollment. |
| GET | `/api/fleet/nodes` | Returns all registered fleet nodes with online status evaluated by `last_heartbeat` (<35s threshold). |
| GET | `/api/fleet/nodes/{id}` | Returns single edge node details. |
| DELETE | `/api/fleet/nodes/{id}` | Deletes edge node and cascades violations. |
| POST | `/api/fleet/nodes/{id}/config` | Queues `update_config` command in `edge_commands` table for delivery on next 3s edge poll. |
| POST | `/api/fleet/nodes/{id}/request_snapshot` | Queues `capture_snapshot` command in `edge_commands`, waits up to 8s for edge reply, and returns live `image_base64` directly to browser without Supabase storage pileup. |
| POST | `/api/fleet/nodes/{id}/trigger_sync` | Queues `trigger_sync` command in `edge_commands` to force immediate batch synchronization. |
| GET | `/api/fleet/violations` | Queries Supabase `fleet_violations` with category/hotel/date/limit filters, returning permanent Supabase Storage CDN URLs. |
| POST | `/api/fleet/violations/{id}/acknowledge` | Marks violation reviewed with admin username and timestamp. |
| GET | `/api/fleet/analytics` | Aggregates daily trends, hourly distribution, and category compliance scores from PostgreSQL. |
| GET, POST | `/api/settings` | Reads and updates central system key-value settings. |

---

## 7. Violation Data Flow (End to End)

1. Camera thread reads a frame (`camera_manager._run`).
2. YOLO runs under the global inference lock; annotated frame is produced.
3. Violation labels are collected with their max confidence.
4. Each class appends 1/0 to its AMFV deque; ratio is computed.
5. Ratio crosses its threshold and the class is not already confirmed:
   confirm it; if cooldown elapsed, call `on_violation`.
6. `on_violation` writes the watermarked annotated JPEG to `snapshots/`,
   inserts a DB row, and spawns email/webhook threads. Central delivery waits
   for the batch-sync ledger.
7. Frontend polls `/logs`, `/stats`, `/amfv_status` every 2.2s and renders the
   log entry, KPI counts, and AMFV bars.
8. Snapshot gallery reads `/snapshots_list`; the review action calls the
   acknowledge endpoint.
9. CSV/analytics read persisted violations.

Fleet path (when the central server is running):

10. Edge `EdgeSyncManager` enrolls via `/api/edge/request_connection`, persists
    `kitchen_id` + `auth_token`, and opens the token-authenticated WebSocket.
11. Edge heartbeats every 10s over WS, including telemetry, cameras, and
    `unsynced_incidents`. Central returns queued commands (HTTP fallback).
12. Confirmed violations stay local with `synced_to_central=0`. Hourly, on
    connect, on demand, or on a central `trigger_sync`, the edge batches up to
    200 unsynced rows to `/api/edge/batch_sync` with base64 snapshots. Central
    deduplicates by `(edge_id, local_violation_id)`, writes evidence, and returns
    the accepted IDs; only then does the edge mark the ledger synced.
13. Central admin polls fleet overview/nodes, requests live snapshots, triggers
    syncs, reviews evidence, acknowledges incidents, pushes AMFV config over the
    duplex channel, and proxies edge live streams.

---

## 8. Configuration and Defaults (Actual Code)

| Setting | Code default | Notes |
| :--- | :--- | :--- |
| AMFV window | 2 frames | `camera_manager.py:20`; UI/README often say 10. |
| Pest threshold | 0.20 | `camera_manager.py:21`. |
| Hygiene threshold | 0.40 | `camera_manager.py:22`. |
| Alert cooldown | 30s | Per camera/class. |
| YOLO confidence | Ultralytics default | No explicit `conf` passed in `_process_frame`. |
| Geometric/aspect filter | Not implemented | Only present in docs/UI. |
| TTA | Not implemented | Only present in settings UI payload. |
| Input size / IoU | Not applied | Model call uses defaults; UI values are ignored by backend. |
| MJPEG pacing | ~0.03s/frame | `generate_mjpeg`. |
| Reconnect max delay | 30s | Exponential from 2s. |
| Detection lock | Global | All cameras serialize inference. |
| DB mode | WAL | Thread-local connections. |
| Default seeded camera | `cam_main` | Only if DB has zero cameras; prefers `demo1.mp4`. |
| Edge central URL | `http://127.0.0.1:9000` | Env `CENTRAL_SERVER_URL`; persisted `central_url` wins when set. |
| Edge API URL | `http://127.0.0.1:8000` | Env `EDGE_API_URL`, advertised during enrollment. |
| Edge batch limit | 200 incidents | `EdgeSyncManager.BATCH_LIMIT`; central rejects >500. |
| Edge sync interval | 60 minutes | Returned by central; persisted `sync_interval_minutes`. |
| Edge heartbeat | 10s | Over WS; HTTP heartbeat only when duplex is unavailable. |
| Main server bind | `0.0.0.0:8000` via `__main__` | `uvicorn main:app --reload` binds 127.0.0.1 by default. |

Settings keys actually observed in the committed DB:
`conf_threshold`, `iou_threshold`, `imgsz`, `geometric_filter`, `enable_tta`,
`amfv_window`, `amfv_threshold_pest`, `amfv_threshold_hygiene`,
`cooldown_seconds`, `notification_email`, `webhook_url`, `edge_id`.
Only the AMFV/cooldown/notification/webhook subset is consumed by the backend.

Central server defaults (`D:\Projects\SHMS_central_server\config.py`):

| Setting | Default | Env override |
| :--- | :--- | :--- |
| Bind host / port | `0.0.0.0` / `9000` | `SHMS_CENTRAL_HOST`, `SHMS_CENTRAL_PORT` |
| Session secret | `shms-enterprise-central-secret-key-2026-v1` | `SHMS_SECRET_KEY` |
| Session cookie | `shms_central_session`, 24h, HttpOnly, SameSite=Lax, not Secure | none |
| Heartbeat timeout / check | 30s / 10s | none (constants only) |
| Database | `<central folder>/central_monitoring.db` | none |
| Snapshot dir | `<central folder>/central_snapshots` | none |
| Default admin | `admin` / `admin123` | `SHMS_ADMIN_USER`, `SHMS_ADMIN_PASS` |
| Edge auth token | generated per node, no expiry | none; stored as HMAC-SHA256 digest in `edge_nodes.auth_token` |
| Duplex snapshot timeout | 5s | none (constant in `request_snapshot`) |
| Snapshot upload limits | 5 MB each / 25 MB batch | none (constants in `server.py`/`edge_sync.py`) |

The `heartbeat_timeout` value saved in `/api/settings` is not read by the
background health monitor.

---

## 9. Run, Build, and Validate

### Prerequisites

- Python 3.10+ (repo tested here with 3.14.3).
- Node 18+ / npm (tested with Node 22.20.0, npm 11.6.0).
- Backend packages: `fastapi`, `uvicorn`, `ultralytics`, `opencv-python`,
  `jinja2`, `numpy`, `pyyaml`, `websocket-client`; optional `psutil` (edge
  telemetry) and `roboflow` (dataset download). `pip install -r requirements.txt`.
- Central needs `websockets` (or `uvicorn[standard]`) or the `/ws/edge/...`
  endpoint returns 404 during the upgrade.

### Single-Command Instant Launch (Recommended)

The Edge Node includes native zero-friction launchers that auto-detect Python, verify virtual environments, execute pre-flight checks, boot FastAPI/Uvicorn, and open the dashboard in the default browser:

```powershell
# Windows Command Prompt or double-click in Explorer:
run.bat

# Windows PowerShell:
.\run.ps1

# Cross-platform / direct Python:
python run.py

# Using npm (root package.json):
npm start
```

### Production mode (Manual Steps)

```powershell
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python -m uvicorn main:app --reload
# open http://127.0.0.1:8000
```

The root route reads `frontend/dist/index.html` directly. `templates/index.html`
is only a fallback. The README's "copy dist/index.html to templates" step is
optional/stale, not required for the main path.

### Development mode (Vite HMR)

```powershell
# terminal 1
python -m uvicorn main:app --reload
# terminal 2
cd frontend
npm run dev
# open http://localhost:3000  (proxied to :8000)
```

### Mobile camera relay

```powershell
python mobile_stream_server/server.py
# laptop: http://localhost:8080     phone: http://<LAN-IP>:8080/camera
# add HTTP source http://127.0.0.1:8080/video in the main dashboard
```

### Central fleet server (sibling folder)

```powershell
cd D:\Projects\SHMS_central_server
npm install
# Configure .env with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, etc.
npm run dev
# admin: http://localhost:9000/admin    default login: admin / admin123

# Deploy to Vercel
vercel
```

Enroll the edge from the dashboard (Central button) with
`http://<central-host>:9000` (or `https://<your-project>.vercel.app`).
Once enrolled, credentials persist and the edge polls central automatically every 3 seconds.
If central is unreachable, the edge keeps retrying with backoff.

Vercel Deployment: The central server is **100% Vercel-ready** via `vercel.json`,
backed by PostgreSQL on Supabase (`supabase_schema.sql`) and Supabase Storage for
violation frames (`evidence-snapshots`). Live snapshots are ephemeral base64
without storage pileup, and batch sync sends permanent CDN URLs to stay under
Vercel's 4.5 MB request limit.

### Fine-tuning

```powershell
python train_finetune.py --data path\to\data.yaml --epochs 50 --deploy
# or Roboflow:
python train_finetune.py --rf-key KEY --rf-workspace WS --rf-project PROJ --rf-version 1 --deploy
```

### Validation commands

```powershell
# main/edge app
python -m compileall -q main.py database.py camera_manager.py edge_sync.py train_finetune.py mobile_stream_server\server.py
cd frontend
npm run lint
npm run build

# central server (sibling folder)
cd D:\Projects\SHMS_central_server
node -c api/index.js server.js lib/db.js lib/auth.js lib/supabase.js
cd frontend
npm run build
```

Current status: edge Python AST and compileall pass; `npm run lint` passes;
edge and central Vite builds pass. Central Node.js syntax checks pass.
Approach B integration (HTTP poll + command reply + direct Supabase Storage batch sync)
is verified.

### Git hygiene

`.gitignore` ignores `/snapshots`, `runs/`, `*.backup_*`, `datasets/`, `__pycache__/`,
`hotel_monitoring.db*`, `*.db`, `*.db-shm`, `*.db-wal`, `.env`, and `.env.*`.
Models (`best.pt`, `best.onnx`) and demo videos are tracked.

---

## 10. Known Issues and Documentation Gaps

These reflect current code reality:

1. **AMFV & Noise Filtering Active**: Two-tier filtering is now active: Tier 1 Confidence
   Calibration (`conf >= conf_threshold`) and Tier 2 Geometric Noise Filter (aspect ratio `> 7.0`
   and minimum dimension `< 12px` ignored).
2. **Persisted Settings Applied at Startup**: `startup_event` in `main.py` reads saved
   detection/AMFV settings from DB and applies them to all stream instances on startup.
3. **Settings API Fully Wired**: `GET /settings` and `POST /settings` store and return
   `conf_threshold`, `imgsz`, `geometric_filter`, `enable_tta`, `iou_threshold`, `amfv_window`,
   and `cooldown_seconds`.
4. **Analytics Response Alignment**: `by_camera` query in `database.py` strictly respects
   the `camera_id` filter when provided.
5. **Dynamic AMFV Window Size**: `/amfv_status` reports dynamic `self.amfv_window_size` rather
   than a static constant.
6. **Email Toggle Respected**: `on_violation` strictly verifies `email_alerts_enabled` before
   dispatching.
7. **Secrets Removed**: Hardcoded Gmail credentials removed from source code; camera endpoints
   sanitize URLs via `mask_url_credentials` and strip plaintext passwords.
8. **CORS Security**: Wildcard `*` CORS with credentials removed; configurable origin whitelist
   enforced via `CORS_ORIGINS`.
9. **Central Server Vercel Readiness (RESOLVED)**: Central server rewritten in Node.js / Express
   with `vercel.json`, PostgreSQL in Supabase, and Supabase Storage bucket integration.
10. **Snapshot Payload Cap**: Bypassed Vercel's 4.5 MB request body cap by having the edge
    upload JPEGs directly to Supabase Storage and sending lightweight metadata (< 30 KB) to central.
11. **Live Snapshot Ephemerality**: Live inspection snapshots are delivered directly as base64
    via `/api/edge/command_reply`, ensuring zero storage pileup in Supabase.
12. **Visual-only accuracy claims**: "AMFV Accuracy 99.2%" in the analytics modal is hardcoded UI display.

---

## 11. Conventions and Change Guide

### Code conventions

- Backend (Edge): plain Python modules; per-camera daemon threads; thread-local DB connections;
  global YOLO inference lock; `NotificationHub` alert dispatcher; 3s HTTP polling edge sync.
- Backend (Central): Node.js 22 / Express serverless app (`api/index.js`); `@supabase/supabase-js`
  for database & storage; JWT session cookies; HMAC edge token verification.
- Frontend: functional React 19 components with hooks; Tailwind utility classes; shadcn UI primitives.
- API errors use standard HTTP status codes with `{detail: ...}` JSON.

---

## 12. Change Log

| Date | Commit/State | Change |
| :--- | :--- | :--- |
| 2026-11-13 | `57e3b6a` | Initial end-to-end analysis captured in this file. |
| 2026-11-14 | Working tree | Added forensic HUD watermarking in `utils/watermark.py`; `on_violation` uses `save_watermarked_snapshot` with a plain `cv2.imwrite` fallback. |
| 2026-11-14 | Working tree | Added central ReportLab compliance PDF in `utils/pdf_report.py` and `/api/fleet/export/pdf`. |
| 2026-11-14 | Working tree | Added enterprise duplex sync: edge `EdgeSyncManager`, sync-ledger migration, central token-auth WS + idempotent batch ingestion. |
| 2026-11-14 | Working tree | Security audit & regression hardening: removed hardcoded credentials, replaced wildcard CORS with origin whitelist, wired `NotificationHub` from `utils.alert_dispatcher.py` for anti-spam rate limiting and responsive HTML alerts, fixed `email_alerts_enabled` toggle bug, sanitized camera endpoints (`mask_url_credentials`), fixed info disclosure in `/snapshots_list`, wired saved calibration settings to startup, added geometric noise filter and confidence calibration to `camera_manager.py`, capped mobile stream WebSocket frames at 5 MB, replaced `os.system` with `subprocess.run` in `train_finetune.py`, and updated `.gitignore`. |
| 2026-11-14 | Working tree | Architecture comparison (Render vs Fly.io vs GCP vs Vercel); user selected Approach B (Vercel Serverless + Supabase PostgreSQL & Storage). |
| 2026-11-15 | Working tree | **Central Server Rewrite (Node.js / Express on Vercel)**: Created `package.json`, `vercel.json`, `supabase_schema.sql`, `lib/supabase.js`, `lib/auth.js`, `lib/db.js`, `api/index.js`, and `server.js` in `D:\Projects\SHMS_central_server`. Backed by PostgreSQL in Supabase and Supabase Storage bucket `evidence-snapshots`. |
| 2026-11-15 | Working tree | **Edge Sync Modernization (Approach B)**: Transitioned `edge_sync.py` to a 3-second HTTP Poller (`POST /api/edge/poll`). Added direct Supabase Storage snapshot uploads (`_upload_snapshot_to_supabase`) bypassing Vercel's 4.5 MB limit. Added ephemeral base64 live snapshots via `/api/edge/command_reply` with zero Supabase storage pileup. Updated `opencode.md` reference. |
