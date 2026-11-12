# Smart Hotel Monitoring System — Enterprise CCTV AI Surveillance

An automated enterprise AI surveillance and compliance platform engineered for hotel and commercial kitchens. This system continuously monitors multiple concurrent CCTV camera streams using **YOLOv8** computer vision backed by a **4-Tier False-Positive Suppression Pipeline** and **AMFV (Adaptive Multi-Frame Verification)** to detect hygiene compliance breaches (missing aprons, gloves, or hairnets) and pest incursions (cockroaches, lizards, or rats).

The interface is built with **React 19**, **Tailwind CSS**, and **shadcn UI**, designed in a sleek **monotonous ash grey and crisp white** industrial aesthetic.

---

## 🚀 Key Highlights

* **Dedicated React 19 & shadcn UI Architecture**:
  * Pure **shadcn UI** primitives (Dialog, Tabs, Progress, Slider, Switch, DropdownMenu, Badge, Button, Input, Card).
  * **Monotonous Ash Grey & Crisp White Theme**: Minimalist, distraction-free carbon & zinc palette (`#0f0f12`, `#18181c`, `#29292e`) with isolated functional alert accents (Crimson `#ef4444` for pests, Amber `#f59e0b` for hygiene, Emerald `#10b981` for active streams).
  * **Video-First Workspace**: Maximizes CCTV viewing canvas with 16:9 proportioned video stages and a 1-click **Collapse Inspector** toggle for true 100% full-width surveillance.
* **Slim 36px KPI Status Strip (`KpiStrip.jsx`)**:
  * Replaced bulky metric cards with a compact, high-density status strip tracking Total Violations, Pest Incursions, Hygiene Breaches, AMFV Consensus State, and View Modes.
* **Unified Tabbed Inspector Dock (`InspectorDock.jsx`)**:
  * Clean 3-in-1 inspector panel (`Logs`, `AMFV Consensus`, and `Cameras`) with single-active conditional rendering—zero phantom whitespace, zero vertical cut-offs, and full-height smooth scrolling.
* **4-Tier False-Positive Suppression Pipeline**:
  * **Tier 1 (Confidence Calibration)**: Rejects low-confidence detections below 45% ($\ge 0.45$).
  * **Tier 2 (Geometric Aspect & Size Ratio Filter)**: Discards bounding box noise (area ratio $< 0.10$, bounding box height/width aspect ratios $< 6.0$, pixel noise $< 16\text{px}$).
  * **Tier 3 (Adaptive Multi-Frame Verification - AMFV)**: Enforces temporal rolling consensus ($W = 10$ frames $\sim 0.6\text{s}$ window) where detections must be confirmed by $\frac{1}{W} \sum D_c(t-i) \ge \tau$ before logging an infraction.
  * **Tier 4 (Time-Based Cooldown)**: Configurable alert cooldown (30s default) to prevent spamming while threats persist.
* **Multi-Camera CCTV Support**:
  * Stream RTSP IP cameras, HTTP/MJPEG streams, USB webcams, or video files (`demo1.mp4`).
  * CCTV Connection Wizard with presets for Hikvision, Dahua, Reolink, Mobile IP Webcams, and Generic RTSP.
  * Unclipped 3-dot dropdown menu for filtering stats and removing cameras.
* **Automated Multi-Channel Dispatch**:
  * Real-time Gmail SMTP alert notifications with attached high-resolution evidence snapshots.
  * Configurable Webhook dispatcher for Slack, Discord, or Microsoft Teams.
* **Comprehensive Audit & Analytics**:
  * Interactive Chart.js analytics modal (7-day violation trends and 24-hour peak risk distribution).
  * Evidence snapshot gallery with zoom inspector and staff review sign-offs.
  * One-click CSV audit trail export (`/export/csv`).

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite 8, Tailwind CSS v3, shadcn UI, Radix UI Primitives, Lucide Icons, Chart.js |
| **Backend** | FastAPI (Python), Uvicorn, Starlette |
| **Computer Vision** | Ultralytics YOLOv8 (`best.pt`, `best.onnx`), OpenCV (`cv2.VideoCapture`) |
| **Database** | SQLite3 (WAL mode, thread-safe connections) |
| **Alerts & Exports** | Python `smtplib`, `email.message`, CSV Streaming |

---

## 📂 Project Structure

```
Smart-hotel-monitoring-system/
├── camera_manager.py           # Multi-threaded RTSP capture, AMFV engine, geometric filter
├── database.py                 # SQLite WAL persistence layer for cameras, logs, & settings
├── main.py                     # FastAPI application, streaming endpoints, static mounts
├── train_finetune.py           # YOLOv8 fine-tuning script for hotel PPE datasets
├── best.pt                     # YOLOv8 PyTorch model weights (Pests + PPE classes)
├── best.onnx                   # ONNX optimized model export
├── demo1.mp4                   # Active CCTV surveillance test video
├── hotel_monitoring.db         # Persistent SQLite database
├── snapshots/                  # Auto-captured violation evidence images
├── templates/
│   └── index.html              # Synchronized React application entry point
└── frontend/
    ├── package.json            # Node dependencies & build scripts
    ├── tailwind.config.js      # Tailwind CSS configuration with shadcn HSL variables
    ├── vite.config.js          # Vite build & proxy configuration
    ├── dist/                   # Production React build served directly by FastAPI
    │   ├── index.html
    │   └── assets/             # Bundled JS and CSS assets
    └── src/
        ├── App.jsx             # Top-level state orchestration & layout
        ├── index.css           # Ash grey & white design tokens
        ├── components/
        │   ├── Navbar.jsx              # Header, live clock, modal launchers
        │   ├── KpiStrip.jsx            # Slim 36px horizontal metric strip
        │   ├── CameraGrid.jsx          # Hero video canvas, 16:9 stage, Focus mode
        │   ├── InspectorDock.jsx       # 3-in-1 tabbed panel (Logs, AMFV, Cameras)
        │   ├── AddCameraModal.jsx      # CCTV connection wizard & RTSP presets
        │   ├── AnalyticsModal.jsx      # Time-series charts & hourly peak distribution
        │   ├── SettingsModal.jsx       # Real-time AMFV & alert sensitivity controls
        │   ├── SnapshotGalleryModal.jsx # Evidence snapshot gallery with zoom
        │   └── ui/                     # Modular shadcn UI primitives
        └── services/
            └── api.js                  # Centralized REST API client
```

---

## ⚙️ Quick Start Guide

### 1. Python Environment & Dependencies

Install required backend packages:
```bash
pip install fastapi ultralytics opencv-python uvicorn jinja2
```

### 2. Run the Surveillance Server

Start the application with Uvicorn:
```bash
python -m uvicorn main:app --reload
```

Open your browser and navigate to:
```
http://127.0.0.1:8000
```
FastAPI automatically serves the dedicated React application from `frontend/dist/`.

*(Optional: For frontend hot-reloading development, run `cd frontend && npm run dev` on `http://localhost:3000`).*

---

## 📹 Adding a CCTV Camera Stream

1. Click **+ Add Camera** in the top navigation bar.
2. Select your stream type:
   * **RTSP IP Cam**: Choose your brand preset (Hikvision, Dahua, Reolink, Mobile Webcam, or Generic), enter the IP, Port, Username, and Password.
   * **HTTP Stream**: For browser/app streams (e.g. `http://192.168.1.100:8080/video`).
   * **USB Webcam**: Enter device index (default: `0`).
   * **Video File**: Enter local file path (e.g. `demo1.mp4`).
3. Click **Test Connection** to verify connectivity and preview the resolution.
4. Click **Add Camera Stream** to launch the live AI monitoring worker.

---

## 🛡️ Monitored Violation Classes

| Category | Classes | Alert Color | AMFV Threshold |
| :--- | :--- | :--- | :--- |
| **Pests** | `cockroach`, `lizard`, `rat` | Crimson (`#ef4444`) | $35\%$ consensus ($4/10$ frames) |
| **Hygiene / PPE** | `no_apron`, `no_gloves`, `no_hairnet` | Amber (`#f59e0b`) | $45\%$ consensus ($5/10$ frames) |

---

## 🔌 API Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the dedicated React + shadcn UI single-page application |
| `GET` | `/video_feed/{camera_id}` | Multipart MJPEG live video stream with dual-state bounding box overlays |
| `GET` | `/cameras` | List all configured CCTV cameras and connection states |
| `POST` | `/cameras` | Register a new camera stream (RTSP/HTTP/Webcam/File) |
| `DELETE` | `/cameras/{camera_id}` | Remove a camera stream and stop worker thread |
| `GET` | `/logs` | Retrieve recent violation incident records with snapshot URLs |
| `POST` | `/clear_logs` | Clear audit logs (optionally filtered by camera) |
| `GET` | `/stats` | Aggregate violation totals and class breakdowns |
| `GET` | `/amfv_status` | Real-time temporal rolling frame ratios and active confirmations |
| `GET` | `/analytics` | Historical 7-day daily incident trend & 24h hourly distribution |
| `GET` | `/export/csv` | Download complete violation audit trail as a `.csv` file |
| `GET` | `/settings` | Fetch detection parameters and notification settings |
| `POST` | `/settings` | Dynamic runtime calibration of confidence, AMFV window, and thresholds |
| `GET` | `/snapshots/{filename}` | Serve high-resolution violation evidence snapshot images |

---

## 📄 License
This project is proprietary and developed for smart enterprise hotel kitchen surveillance and compliance monitoring.
