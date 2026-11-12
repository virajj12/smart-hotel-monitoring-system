"""
Mobile CCTV Stream Server
Enables using any Android/iPhone mobile camera as a live CCTV feed over local Wi-Fi.
Transmits frames via WebSockets and broadcasts a standard HTTP MJPEG stream at /video.
"""

import os
import socket
import time
import asyncio
import threading
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import cv2
import numpy as np

app = FastAPI(title="Mobile CCTV Stream Server")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global Frame Buffer & Telemetry
latest_frame_bytes: Optional[bytes] = None
frame_lock = threading.Lock()
connected_phones = set()
frame_counter = 0
current_fps = 0
last_fps_time = time.time()
last_frame_received_time = 0.0


def get_local_ip() -> str:
    """Detect the local Wi-Fi / LAN IP of this laptop."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to an external address to get default outbound interface (does not send packets)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def create_standby_frame(message: str = "Waiting for Mobile Camera...") -> bytes:
    """Generate a clean dark standby placeholder frame."""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (18, 17, 15)  # Dark ash background

    # Subtle grid
    for x in range(0, 1280, 80):
        cv2.line(img, (x, 0), (x, 720), (28, 27, 24), 1)
    for y in range(0, 720, 80):
        cv2.line(img, (0, y), (1280, y), (28, 27, 24), 1)

    # Text overlays
    cv2.putText(img, "MOBILE CCTV STREAM RELAY", (420, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.putText(img, message, (400, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (160, 160, 160), 2, cv2.LINE_AA)
    cv2.putText(img, "Open mobile camera link on your phone (same Wi-Fi)", (370, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1, cv2.LINE_AA)

    _, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return encoded.tobytes()


STANDBY_FRAME = create_standby_frame()


# ── Web Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Laptop Dashboard with QR Code, URL helpers, and live video preview."""
    local_ip = get_local_ip()
    port = 8080
    mobile_url = f"http://{local_ip}:{port}/camera"
    stream_url = f"http://127.0.0.1:{port}/video"

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mobile_url": mobile_url,
            "stream_url": stream_url,
            "local_ip": local_ip,
            "port": port,
        }
    )


@app.get("/camera", response_class=HTMLResponse)
async def camera_page(request: Request):
    """Mobile phone camera capture web client."""
    return templates.TemplateResponse(request=request, name="camera.html")


# ── WebSocket Frame Receiver ──────────────────────────────────────────

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Receives binary JPEG frame buffers from mobile phone camera."""
    global latest_frame_bytes, frame_counter, current_fps, last_fps_time, last_frame_received_time
    await websocket.accept()
    connected_phones.add(websocket)
    print("📱 Mobile phone camera connected via WebSocket!")

    try:
        while True:
            # Receive binary JPEG data from phone
            data = await websocket.receive_bytes()
            if data and len(data) > 100:
                with frame_lock:
                    latest_frame_bytes = data
                    last_frame_received_time = time.time()
                    frame_counter += 1

                # Update FPS
                now = time.time()
                if now - last_fps_time >= 1.0:
                    current_fps = frame_counter
                    frame_counter = 0
                    last_fps_time = now

    except WebSocketDisconnect:
        print("📱 Mobile phone camera disconnected.")
    except Exception as e:
        print(f"⚠️ WebSocket error: {e}")
    finally:
        connected_phones.discard(websocket)


# ── HTTP MJPEG Stream Provider ────────────────────────────────────────

def mjpeg_generator():
    """Continuously yield multipart JPEG boundaries for HTTP MJPEG consumers."""
    global latest_frame_bytes, last_frame_received_time

    while True:
        frame = None
        now = time.time()

        with frame_lock:
            # If received frame within the last 3.5 seconds, stream it
            if latest_frame_bytes and (now - last_frame_received_time < 3.5):
                frame = latest_frame_bytes
            else:
                frame = STANDBY_FRAME

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.033)  # ~30 FPS throttle


@app.get("/video")
@app.get("/video_feed")
def get_video_stream():
    """
    Standard HTTP MJPEG stream endpoint.
    Compatible with OpenCV cv2.VideoCapture("http://127.0.0.1:8080/video").
    """
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/snapshot")
def get_snapshot():
    """Return single JPEG snapshot of current camera frame."""
    with frame_lock:
        frame = latest_frame_bytes or STANDBY_FRAME
    return Response(content=frame, media_type="image/jpeg")


@app.get("/status")
def get_status():
    """Telemetry endpoint returning connection status and FPS."""
    now = time.time()
    is_active = len(connected_phones) > 0 and (now - last_frame_received_time < 3.0)
    return JSONResponse({
        "connected": is_active,
        "phones_connected": len(connected_phones),
        "fps": current_fps if is_active else 0,
        "local_ip": get_local_ip(),
        "port": 8080,
    })


# ── Main Entrypoint ───────────────────────────────────────────────────

def run_server():
    ip = get_local_ip()
    port = 8080

    print("=" * 68)
    print("🚀 MOBILE CCTV STREAM SERVER RUNNING")
    print("=" * 68)
    print(f"💻 Laptop Local IP : {ip}")
    print(f"🌐 Laptop Dashboard: http://localhost:{port}")
    print(f"📱 Mobile Camera   : http://{ip}:{port}/camera")
    print(f"📹 HTTP Stream URL : http://127.0.0.1:{port}/video")
    print("=" * 68)
    print("👉 NOTE ON MOBILE BROWSER SECURITY (Chrome/Safari):")
    print(f"   Mobile browsers require camera permissions to be enabled:")
    print(f"   1. On Android Chrome, open: chrome://flags/#unsafely-treat-insecure-origin-as-secure")
    print(f"   2. Add: http://{ip}:{port} -> Set to ENABLED -> Tap Relaunch.")
    print("   OR USE IP WEBCAM APP:")
    print("   Install 'IP Webcam' on phone -> Tap 'Start Server' -> Add its URL directly!")
    print("=" * 68)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()

