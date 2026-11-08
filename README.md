# Smart Hotel Monitoring System — Multi-Camera CCTV Surveillance

An automated enterprise AI surveillance solution designed for smart hotels to monitor kitchen environments in real-time across multiple CCTV camera streams. This system leverages **YOLOv8** computer vision with **AMFV (Adaptive Multi-Frame Verification)** to detect hygiene violations (missing aprons, gloves, or hairnets) and pest activity (cockroaches, lizards, or rats).

## 🚀 Key Features

* **Multi-Camera CCTV Support**: Manage multiple concurrent camera streams (RTSP CCTV, HTTP IP cameras, USB webcams, or video files) with independent threaded capture and inference.
* **CCTV Connection Wizard**: Connect to commercial CCTV brands (Hikvision, Dahua, Reolink, or Generic RTSP) with automated URL formatting and live connection test with thumbnail preview.
* **Dynamic Multi-Grid Dashboard**: Dark-mode glassmorphic interface displaying live multi-camera feeds, focus mode (click to expand any camera tile), per-camera status pills, and FPS counters.
* **Real-time AI Detection with AMFV**: YOLOv8 temporal rule-based decision engine ($V_c = 1 \text{ if } \frac{1}{W} \sum D_c(t-i) \ge \tau$) preventing false positives from transient occlusions.
* **SQLite Persistence Layer**: Thread-safe persistent database (`hotel_monitoring.db`) in WAL mode tracking camera registries, violation histories, AMFV ratios, and snapshot references across server restarts.
* **Automated Multi-Channel Alerts**: Notifies management via Gmail SMTP (with attached snapshot evidence tagged by camera location and timestamp) and configurable HTTP Webhooks.
* **Time-Series Analytics (Chart.js)**: Interactive analytics modal featuring a 14-day daily violation trend line chart, 24-hour kitchen violation timeline heatmap, and zone-by-zone camera distribution.
* **Evidence Snapshot Gallery**: Dedicated visual review gallery where staff can filter snapshots by category or camera, zoom evidence images, and mark violations as reviewed/acknowledged.
* **One-Click CSV Export**: Download complete compliance and violation audit logs as a `.csv` spreadsheet at any time (`/export/csv`).
* **Live System Settings UI**: Tune AMFV rolling window size, pest sensitivity thresholds, hygiene PPE thresholds, alert cooldowns, and notification targets directly from the web interface without restarting the server.
* **Per-Camera Log Filtering & Analytics**: View global statistics or isolate violations by camera, severity, or violation class (Pests vs. Hygiene).

## 🛠️ Tech Stack

* **Backend**: FastAPI (Python)
* **AI Model**: Ultralytics YOLOv8 (`best.pt`)
* **Computer Vision**: OpenCV (`cv2.VideoCapture`, MJPEG streaming)
* **Database**: SQLite (WAL mode, thread-local connections)
* **Frontend**: HTML5, CSS3 (Glassmorphism & animations), JavaScript (Async polling, Chart.js)
* **Communication**: SMTP with TLS/SSL for email notifications, HTTP Webhook dispatch

## 📂 Project Structure

* `main.py`: Core FastAPI service providing camera CRUD, video streaming endpoints, CSV export, analytics, and settings APIs.
* `camera_manager.py`: Multi-stream thread coordinator managing `CameraStream` lifecycles, RTSP reconnects, and per-camera AMFV engines.
* `database.py`: SQLite persistence layer for camera configurations, violation logs, settings, and time-series analytics.
* `templates/index.html`: Responsive multi-camera dashboard with live grid, CCTV configuration wizard, analytics charts, snapshot gallery, and settings panel.
* `snapshots/`: Directory where violation evidence images are automatically saved and served.
* `best.pt`: Trained YOLOv8 model weights for pests and hygiene PPE detection.

## 🔧 Setup & Running

### 1. Installation

```bash
pip install fastapi ultralytics opencv-python uvicorn jinja2
```

### 2. Launch Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your web browser.

## 📹 Connecting CCTV Cameras

1. Click **➕ Add Camera** in the top navigation bar.
2. Select **RTSP Stream** (or HTTP, USB Webcam, Video File).
3. Choose your CCTV brand preset (Hikvision, Dahua, Reolink, or Generic).
4. Enter the camera's IP, Port, Username, Password, and Channel.
5. Click **Test Connection** to verify connection and preview the live frame.
6. Click **Add Camera** to start live AI monitoring on that feed.

## 📊 Analytics, Reports & Settings

* **Analytics**: Click **📊 Analytics** in the navbar to review 14-day trends and peak hour violation timelines.
* **Evidence Gallery**: Click **🖼️ Gallery** to inspect all captured violation evidence and sign off on reviews.
* **Settings**: Click **⚙️ Settings** to adjust AMFV thresholds, verification window size, alert cooldown, and email/webhook targets.
* **CSV Report**: Click **📥 CSV Export** in the violation logs panel to download an audit spreadsheet.

## 🚨 Monitored Violations

* **Pests**: Cockroaches, Lizards, Rats.
* **Hygiene**: No Apron, No Gloves, No Hairnet.
