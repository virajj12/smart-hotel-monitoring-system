# Mobile CCTV Stream Server

Turn any Android or iPhone smartphone into a live CCTV camera stream over your local Wi-Fi without needing to install any third-party apps from the Play Store or App Store.

The server captures your phone camera via a web interface, relays frames over a high-speed WebSocket connection, and broadcasts a standard **HTTP MJPEG Stream** at `http://localhost:8080/video`.

---

## 🏗️ Architecture

```
┌────────────────────────┐      Local Wi-Fi      ┌─────────────────────────────┐      Localhost Stream     ┌───────────────────────────────┐
│     Mobile Phone       │  ──────────────────>  │    Mobile Stream Server     │  ──────────────────────>  │ Smart Hotel Monitoring System │
│ (Chrome / Safari / iOS)│      WebSockets       │    (Python / Port 8080)     │      HTTP MJPEG Feed      │     (FastAPI / Port 8000)     │
│  http://<IP>:8080/cam  │      ~25-30 FPS       │     Broadcasts /video       │  http://127.0.0.1:8080/vid│   YOLOv8 & AMFV Processing    │
└────────────────────────┘                       └─────────────────────────────┘                           └───────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Start the Mobile Stream Server

In a separate terminal, run:

```bash
cd mobile_stream_server
python server.py
```
*(Or from the project root: `python mobile_stream_server/server.py`)*

The server will automatically detect your laptop's Wi-Fi IP and display:
```
==================================================================
🚀 MOBILE CCTV STREAM SERVER RUNNING
==================================================================
💻 Laptop Local IP : 192.168.1.50
🌐 Laptop Dashboard: http://localhost:8080
📱 Mobile Camera   : http://192.168.1.50:8080/camera
📹 HTTP Stream URL : http://127.0.0.1:8080/video
==================================================================
```

---

### 2. Connect Your Phone

1. Ensure your mobile phone is connected to the **same Wi-Fi network** as your laptop.
2. Open `http://localhost:8080` in your laptop browser to see the **QR Code**.
3. Scan the QR code with your phone (or open `http://<your-laptop-ip>:8080/camera` in Chrome or Safari).
4. Tap **"▶ Start Streaming"** and allow camera permission.
5. You can toggle between **Front / Back Camera (Flip)**, adjust resolution (**720p / 480p / 1080p**), and turn on the **Torch / Flashlight**.

---

### 3. Connect to the Smart Hotel Monitoring Dashboard

1. Open your main surveillance dashboard at [http://127.0.0.1:8000](http://127.0.0.1:8000).
2. Click **+ Add Camera** in the top navigation bar.
3. Select the **HTTP Stream** tab.
4. Set:
   * **Camera Name**: `Mobile CCTV (Phone)`
   * **Location**: `Kitchen - Station 2`
   * **HTTP Stream URL**: `http://127.0.0.1:8080/video`
5. Click **Test Connection** (you should see the live resolution verified).
6. Click **Add Camera Stream**.

Your phone's camera feed is now an active CCTV camera monitored in real time by YOLOv8 and AMFV!

---

## ⚠️ Troubleshooting: "cannot read properties of undefined (reading 'getUserMedia')"

Mobile browsers (Chrome / Safari) enforce a security rule: **Camera access (`navigator.mediaDevices.getUserMedia`) is disabled on plain `http://IP:PORT` unless marked as secure.**

### Fix in 20 seconds (Chrome on Android):
1. On your phone's Chrome browser, open a new tab and go to:
   ```
   chrome://flags/#unsafely-treat-insecure-origin-as-secure
   ```
2. In the text box, paste your server URL (e.g. `http://192.168.1.50:8080`).
3. Select **Enabled** from the dropdown.
4. Tap **Relaunch** at the bottom right.
5. Refresh the camera page (`http://192.168.1.50:8080/camera`) and tap **Start Streaming**. The camera will immediately work!

---

## 📱 Alternative: Using "IP Webcam" Android App (Zero Browser Flags Required)

If you prefer using the popular Android app **IP Webcam**:
1. Install **IP Webcam** from Google Play Store on your Android phone.
2. Open the app, scroll to the bottom, and tap **Start Server**.
3. The app displays an IP address on your phone screen (e.g. `http://192.168.1.100:8080`).
4. In the Hotel Monitoring System, click **+ Add Camera** $\rightarrow$ **HTTP Stream**.
5. Enter the stream URL: `http://<phone-ip>:8080/video` (e.g., `http://192.168.1.100:8080/video`).
6. Click **Add Camera Stream**.

---

## 🔍 Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Laptop connection hub with QR code and live stream preview |
| `GET` | `/camera` | Mobile phone camera capture interface |
| `WS` | `/ws/stream` | High-speed binary WebSocket receiving camera frames from phone |
| `GET` | `/video` | Standard HTTP MJPEG stream (compatible with OpenCV & browsers) |
| `GET` | `/snapshot` | Returns a single JPEG frame snapshot |
| `GET` | `/status` | Telemetry returning connection state, FPS, and client count |

