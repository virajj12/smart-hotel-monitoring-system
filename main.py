"""
Smart Hotel Monitoring System - FastAPI Application
Supports multi-camera CCTV streams (RTSP/HTTP/Webcam/File),
YOLOv8 violation detection, AMFV verification, SQLite persistence,
and real-time web dashboard.
"""

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ultralytics import YOLO
import cv2
from datetime import datetime
import smtplib
from email.message import EmailMessage
import threading
import time
import os
import uuid
import csv
import io
import json
import urllib.request
import urllib.parse
import mimetypes
from typing import Optional, List, Dict, Any

# Ensure proper MIME types on Windows (prevents Chrome strict MIME type error on module scripts)
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from database import Database
from camera_manager import CameraManager, VIOLATIONS, PESTS

app = FastAPI(title="Smart Hotel Monitoring System")

# Enable CORS for local Vite dev server (e.g. port 3000 / 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# Folder to save snapshot images for emails & dashboard
os.makedirs("snapshots", exist_ok=True)
app.mount("/snapshots", StaticFiles(directory="snapshots"), name="snapshots")

# Mount dedicated React UI static build assets
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
assets_dir = os.path.join(FRONTEND_DIST, "assets")
os.makedirs(assets_dir, exist_ok=True)
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Database & AI Model
db = Database("hotel_monitoring.db")
model = YOLO("best.pt")

# System tracking
system_start_time = time.time()

# Email configuration
SENDER_EMAIL = "vinithmohan2006@gmail.com"
APP_PASSWORD = "bxli unmn pwbv abol"
RECEIVER_EMAIL = "vinithmohan2006@gmail.com"


def send_alert_email(label: str, timestamp: str, image_path: str, camera_name: str = "Kitchen"):
    """Sends an email with violation details and snapshot attachment."""
    receiver = db.get_setting("notification_email", RECEIVER_EMAIL)
    sender = db.get_setting("sender_email", SENDER_EMAIL)
    password = db.get_setting("app_password", APP_PASSWORD)

    try:
        msg = EmailMessage()
        msg["Subject"] = f"⚠️ Hotel Violation Alert: {label.upper()} [{camera_name}]"
        msg["From"] = sender
        msg["To"] = receiver

        msg.set_content(
            f"A hygiene/pest violation was detected in the kitchen.\n\n"
            f"Camera: {camera_name}\n"
            f"Violation: {label}\n"
            f"Time: {timestamp}\n\n"
            f"Please review the attached snapshot for evidence."
        )

        with open(image_path, "rb") as f:
            img_data = f.read()

        safe_ts = timestamp.replace(":", "-").replace(" ", "_")
        msg.add_attachment(
            img_data,
            maintype="image",
            subtype="jpeg",
            filename=f"{camera_name}_{label}_{safe_ts}.jpg",
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        print(f"[{timestamp}] ✅ Alert email sent for {label} on {camera_name} to {receiver}")
    except Exception as e:
        print(f"❌ Failed to send alert email: {e}")


def send_webhook_alert(label: str, timestamp: str, camera_name: str, ratio: float, confidence: float, snapshot_path: str):
    """Sends a webhook notification to an external HTTP URL if configured."""
    webhook_url = db.get_setting("webhook_url", "")
    if not webhook_url:
        return
    try:
        payload = {
            "event": "violation_detected",
            "camera": camera_name,
            "violation": label,
            "category": "pest" if label in PESTS else "hygiene",
            "timestamp": timestamp,
            "amfv_ratio": ratio,
            "confidence": confidence,
            "snapshot_url": f"/snapshots/{os.path.basename(snapshot_path)}",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "SmartHotelMonitor/2.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"[{timestamp}] 🌐 Webhook delivered ({resp.status})")
    except Exception as e:
        print(f"❌ Webhook notification failed: {e}")


def on_violation(
    camera_id: str,
    label: str,
    timestamp: str,
    frame,
    ratio: float,
    confidence: float,
):
    """Callback fired by CameraStream when AMFV confirms a violation."""
    safe_ts = timestamp.replace(":", "-").replace(" ", "_")
    snapshot_filename = f"{camera_id}_{label}_{safe_ts}.jpg"
    snapshot_path = os.path.join("snapshots", snapshot_filename)

    # Save snapshot image
    try:
        cv2.imwrite(snapshot_path, frame)
    except Exception as e:
        print(f"❌ Failed to save snapshot: {e}")

    # Persist in DB
    try:
        db.add_violation(
            camera_id=camera_id,
            label=label,
            timestamp=timestamp,
            amfv_verified=1,
            amfv_ratio=round(ratio, 3),
            snapshot_path=snapshot_path,
            confidence=round(confidence, 3),
        )
    except Exception as e:
        print(f"❌ Failed to save violation in database: {e}")

    # Lookup camera name for notifications
    cam = camera_manager.get_camera(camera_id)
    camera_name = cam.name if cam else camera_id

    print(
        f"[{timestamp}] 🚨 [{camera_name}] AMFV Confirmed: {label} "
        f"(ratio={ratio:.2f}, conf={confidence:.2f})"
    )

    # Dispatch alerts in background threads
    threading.Thread(
        target=send_alert_email,
        args=(label, timestamp, snapshot_path, camera_name),
        daemon=True,
    ).start()

    threading.Thread(
        target=send_webhook_alert,
        args=(label, timestamp, camera_name, ratio, confidence, snapshot_path),
        daemon=True,
    ).start()


# Initialize CameraManager with YOLO model and callback
camera_manager = CameraManager(model=model, on_violation=on_violation)


@app.on_event("startup")
def startup_event():
    """Load enabled cameras from the database and start streaming."""
    saved_cameras = db.list_cameras()
    if not saved_cameras:
        # Auto-seed a default camera so the dashboard has an active feed out of the box
        default_source = "demo1.mp4" if os.path.exists("demo1.mp4") else ("demo.mp4" if os.path.exists("demo.mp4") else "0")
        default_type = "file" if (os.path.exists("demo1.mp4") or os.path.exists("demo.mp4")) else "webcam"
        try:
            db.add_camera(
                camera_id="cam_main",
                name="Kitchen Main Camera",
                source=default_source,
                location="Kitchen - Cooking Station",
                source_type=default_type,
                enabled=1,
            )
            saved_cameras = db.list_cameras()
            print(f"📹 Seeded default camera: Kitchen Main Camera ({default_source})")
        except Exception as e:
            print(f"❌ Failed to seed default camera: {e}")

    for cam in saved_cameras:
        if cam.get("enabled", 1):
            try:
                camera_manager.add_camera(
                    name=cam["name"],
                    source=cam["source"],
                    location=cam.get("location", ""),
                    source_type=cam.get("source_type", "rtsp"),
                    camera_id=cam["id"],
                )
                print(f"📹 Started camera: {cam['name']} ({cam['id']})")
            except Exception as e:
                print(f"❌ Error starting camera {cam['id']}: {e}")


@app.on_event("shutdown")
def shutdown_event():
    """Stop all camera streams gracefully on shutdown."""
    camera_manager.stop_all()


# ── Frontend Web Dashboard ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve dedicated React + shadcn UI dashboard."""
    react_index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(react_index):
        with open(react_index, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                status_code=200,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
            )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )


@app.get("/favicon.svg")
def get_favicon():
    """Serve React app favicon."""
    fav = os.path.join(FRONTEND_DIST, "favicon.svg")
    if os.path.exists(fav):
        return FileResponse(fav)
    raise HTTPException(status_code=404, detail="Favicon not found")


# ── Camera Management API ───────────────────────────────────────────

@app.get("/cameras")
def get_cameras():
    """List all configured cameras with their current live status."""
    db_cameras = db.list_cameras()
    result = []
    for c in db_cameras:
        cam_id = c["id"]
        live_stream = camera_manager.get_camera(cam_id)
        is_online = bool(live_stream and live_stream.connected)
        fps = live_stream.fps if live_stream else 0.0
        frame_count = live_stream.frame_count if live_stream else 0
        running = live_stream.running if live_stream else False

        # Get violation count for this camera
        vstats = db.get_violation_stats(camera_id=cam_id)
        vcount = vstats.get("total", 0)

        result.append({
            "id": cam_id,
            "name": c["name"],
            "source": c["source"],
            "location": c.get("location", ""),
            "source_type": c.get("source_type", "rtsp"),
            "enabled": bool(c.get("enabled", 1)),
            "status": "online" if is_online else "offline",
            "connected": is_online,
            "fps": fps,
            "frame_count": frame_count,
            "running": running,
            "violation_count": vcount,
        })
    return JSONResponse(content=result)


@app.post("/cameras")
async def add_camera(payload: Dict[str, Any] = Body(...)):
    """
    Add a new camera.
    Accepts name, location, source_type, and either source, url, device_index, or file_path.
    """
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Camera name is required")

    source_type = payload.get("source_type", "rtsp").lower()
    location = payload.get("location", "").strip()

    # Determine the actual source string
    if "source" in payload and payload["source"]:
        source = str(payload["source"]).strip()
    elif "url" in payload and payload["url"]:
        source = str(payload["url"]).strip()
    elif "device_index" in payload and payload["device_index"] is not None:
        source = str(payload["device_index"]).strip()
    elif "file_path" in payload and payload["file_path"]:
        source = str(payload["file_path"]).strip()
    elif source_type == "webcam":
        source = "0"
    else:
        source = ""

    if not source:
        raise HTTPException(status_code=400, detail="Camera source or URL is required")

    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    cam_id = f"cam_{uuid.uuid4().hex[:8]}"

    # Save to database
    db_cam = db.add_camera(
        camera_id=cam_id,
        name=name,
        source=source,
        location=location,
        source_type=source_type,
        enabled=1,
        username=username,
        password=password,
    )

    # Start stream in CameraManager
    stream = camera_manager.add_camera(
        name=name,
        source=source,
        location=location,
        source_type=source_type,
        camera_id=cam_id,
    )

    return JSONResponse(content={
        "id": cam_id,
        "name": name,
        "source": source,
        "location": location,
        "source_type": source_type,
        "enabled": True,
        "status": "online" if (stream and stream.connected) else "offline",
        "connected": bool(stream and stream.connected),
        "fps": stream.fps if stream else 0.0,
        "frame_count": stream.frame_count if stream else 0,
        "running": stream.running if stream else False,
        "violation_count": 0,
    })


@app.get("/cameras/{camera_id}")
def get_camera(camera_id: str):
    """Retrieve details for a single camera."""
    c = db.get_camera(camera_id)
    if not c:
        raise HTTPException(status_code=404, detail="Camera not found")

    live_stream = camera_manager.get_camera(camera_id)
    is_online = bool(live_stream and live_stream.connected)
    vstats = db.get_violation_stats(camera_id=camera_id)

    return JSONResponse(content={
        "id": c["id"],
        "name": c["name"],
        "source": c["source"],
        "location": c.get("location", ""),
        "source_type": c.get("source_type", "rtsp"),
        "enabled": bool(c.get("enabled", 1)),
        "status": "online" if is_online else "offline",
        "connected": is_online,
        "fps": live_stream.fps if live_stream else 0.0,
        "frame_count": live_stream.frame_count if live_stream else 0,
        "running": live_stream.running if live_stream else False,
        "violation_count": vstats.get("total", 0),
    })


@app.put("/cameras/{camera_id}")
async def update_camera(camera_id: str, payload: Dict[str, Any] = Body(...)):
    """Update camera configuration."""
    existing = db.get_camera(camera_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Update fields in DB
    updated = db.update_camera(camera_id, **payload)

    # If source or source_type changed, restart the stream
    source_changed = "source" in payload and payload["source"] != existing["source"]
    type_changed = "source_type" in payload and payload["source_type"] != existing["source_type"]

    if source_changed or type_changed:
        camera_manager.remove_camera(camera_id)
        if updated.get("enabled", 1):
            camera_manager.add_camera(
                name=updated["name"],
                source=updated["source"],
                location=updated.get("location", ""),
                source_type=updated.get("source_type", "rtsp"),
                camera_id=camera_id,
            )

    return JSONResponse(content={"status": "updated", "camera": updated})


@app.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str):
    """Remove a camera from the system."""
    camera_manager.remove_camera(camera_id)
    success = db.delete_camera(camera_id)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found")
    return JSONResponse(content={"status": "deleted", "id": camera_id})


@app.post("/cameras/{camera_id}/toggle")
def toggle_camera(camera_id: str):
    """Toggle a camera stream on or off."""
    c = db.get_camera(camera_id)
    if not c:
        raise HTTPException(status_code=404, detail="Camera not found")

    current_enabled = bool(c.get("enabled", 1))
    new_enabled = not current_enabled
    db.update_camera(camera_id, enabled=int(new_enabled))

    if new_enabled:
        camera_manager.add_camera(
            name=c["name"],
            source=c["source"],
            location=c.get("location", ""),
            source_type=c.get("source_type", "rtsp"),
            camera_id=camera_id,
        )
    else:
        camera_manager.remove_camera(camera_id)

    return JSONResponse(content={"id": camera_id, "enabled": new_enabled})


@app.post("/cameras/test")
async def test_camera_connection(payload: Dict[str, Any] = Body(...)):
    """Test a camera stream connection and retrieve a snapshot preview."""
    source_type = payload.get("source_type", "rtsp").lower()

    if "source" in payload and payload["source"]:
        source = str(payload["source"]).strip()
    elif "url" in payload and payload["url"]:
        source = str(payload["url"]).strip()
    elif "device_index" in payload and payload["device_index"] is not None:
        source = str(payload["device_index"]).strip()
    elif "file_path" in payload and payload["file_path"]:
        source = str(payload["file_path"]).strip()
    elif source_type == "webcam":
        source = "0"
    else:
        source = ""

    if not source:
        return JSONResponse(content={
            "success": False,
            "error": "No source or URL provided for testing",
            "resolution": None,
            "preview": None,
        })

    result = CameraManager.test_connection(source, source_type)
    return JSONResponse(content=result)


# ── Live Video Streaming Feeds ──────────────────────────────────────

@app.get("/video_feed/{camera_id}")
def video_feed_camera(camera_id: str):
    """MJPEG stream for a specific camera."""
    stream = camera_manager.get_camera(camera_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Camera stream not found")
    return StreamingResponse(
        stream.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/video_feed")
def video_feed_default():
    """Default video feed (first active camera) for backwards compatibility."""
    all_cams = list(camera_manager.cameras.values())
    if not all_cams:
        raise HTTPException(status_code=404, detail="No active cameras available")
    return StreamingResponse(
        all_cams[0].generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── Logs & Violations API ────────────────────────────────────────────

@app.get("/logs")
def get_logs(
    camera_id: Optional[str] = None,
    label: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Get violation logs with optional camera or label filtering.
    Returns objects structured for the dashboard renderer.
    """
    raw_logs = db.get_violations(camera_id=camera_id, label=label, limit=limit, offset=offset)

    # Build camera lookup cache
    cam_names = {c["id"]: c["name"] for c in db.list_cameras()}

    formatted = []
    for r in raw_logs:
        c_id = r.get("camera_id", "")
        c_name = cam_names.get(c_id, c_id)
        snap_path = r.get("snapshot_path", "")
        snap_file = os.path.basename(snap_path) if snap_path else ""

        formatted.append({
            "id": r["id"],
            "class": r["label"],
            "label": r["label"],
            "timestamp": r["timestamp"],
            "camera_id": c_id,
            "camera_name": c_name,
            "amfv_verified": bool(r.get("amfv_verified", 0)),
            "amfv_ratio": r.get("amfv_ratio", 0.0),
            "confidence": r.get("confidence", 0.0),
            "snapshot": snap_file,
            "snapshot_path": snap_path,
            "acknowledged": bool(r.get("acknowledged", 0)),
        })

    return JSONResponse(content=formatted)


@app.delete("/clear_logs")
def clear_logs(camera_id: Optional[str] = None):
    """Clear logs and reset AMFV state."""
    deleted_count = db.clear_violations(camera_id=camera_id)

    if camera_id:
        stream = camera_manager.get_camera(camera_id)
        if stream:
            stream.reset_amfv()
    else:
        for stream in camera_manager.cameras.values():
            stream.reset_amfv()

    return JSONResponse(content={
        "status": "cleared",
        "deleted_count": deleted_count,
        "camera_id": camera_id,
    })


@app.post("/violations/{violation_id}/acknowledge")
def acknowledge_violation(violation_id: int):
    """Mark a violation as acknowledged by staff."""
    success = db.acknowledge_violation(violation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Violation not found")
    return JSONResponse(content={"status": "acknowledged", "id": violation_id})


# ── Statistics & AMFV Verification Status ────────────────────────────

@app.get("/stats")
def get_stats(camera_id: Optional[str] = None):
    """Aggregate statistics for all cameras or a specific camera."""
    raw = db.get_violation_stats(camera_id=camera_id)
    total = raw.get("total", 0)
    pest = raw.get("pest", 0)
    hygiene = raw.get("hygiene", 0)
    breakdown = raw.get("breakdown", {})

    # Ensure all violations exist in breakdown dictionary
    full_breakdown = {v: breakdown.get(v, 0) for v in VIOLATIONS}

    return JSONResponse(content={
        "total": total,
        "total_violations": total,
        "pest": pest,
        "pest_detections": pest,
        "hygiene": hygiene,
        "hygiene_issues": hygiene,
        "breakdown": full_breakdown,
        "camera_id": camera_id,
    })


@app.get("/amfv_status")
def get_amfv_status(camera_id: Optional[str] = None):
    """
    Current AMFV rolling-window confirmation ratios.
    Compatible with both per-class dictionary access and legacy ratios format.
    """
    if camera_id:
        stream = camera_manager.get_camera(camera_id)
        if stream:
            amfv_data = stream.get_amfv_status()
            ratios = amfv_data["ratios"]
            confirmed_set = set(amfv_data["confirmed"])
            thresholds = amfv_data["thresholds"]
        else:
            ratios = {v: 0.0 for v in VIOLATIONS}
            confirmed_set = set()
            thresholds = {v: 0.4 for v in VIOLATIONS}
    else:
        # Aggregate across all online cameras (take maximum ratio and union of confirmed)
        ratios = {v: 0.0 for v in VIOLATIONS}
        confirmed_set = set()
        thresholds = {
            "cockroach": 0.2, "lizard": 0.2, "rat": 0.2,
            "no_apron": 0.4, "no_gloves": 0.4, "no_hairnet": 0.4,
        }

        for stream in camera_manager.cameras.values():
            if stream.connected:
                s_amfv = stream.get_amfv_status()
                for v in VIOLATIONS:
                    ratios[v] = max(ratios[v], s_amfv["ratios"].get(v, 0.0))
                confirmed_set.update(s_amfv["confirmed"])

    response_data = {
        v: {
            "ratio": round(ratios.get(v, 0.0), 3),
            "threshold": thresholds.get(v, 0.4),
            "confirmed": v in confirmed_set,
        }
        for v in VIOLATIONS
    }
    response_data["ratios"] = ratios
    response_data["confirmed"] = list(confirmed_set)
    response_data["thresholds"] = thresholds
    response_data["window_size"] = 2

    return JSONResponse(content=response_data)


@app.get("/system_info")
def get_system_info():
    """System health, uptime, and camera statistics."""
    uptime = time.time() - system_start_time
    total_cams = len(db.list_cameras())
    online_cams = sum(1 for s in camera_manager.cameras.values() if s.connected)
    total_frames = sum(s.frame_count for s in camera_manager.cameras.values())

    return JSONResponse(content={
        "model": "best.pt",
        "uptime_seconds": round(uptime, 1),
        "total_cameras": total_cams,
        "online_cameras": online_cams,
        "total_frames_processed": total_frames,
        "violations_monitored": VIOLATIONS,
    })


# ── CSV Export & Reporting ───────────────────────────────────────────

@app.get("/export/csv")
def export_violations_csv(camera_id: Optional[str] = None):
    """Export violation history as a downloadable CSV spreadsheet."""
    violations = db.get_violations(camera_id=camera_id, limit=5000)
    cam_map = {c["id"]: c["name"] for c in db.list_cameras()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Violation ID", "Camera ID", "Camera Name", "Violation Type",
        "Category", "Timestamp", "AMFV Verified", "AMFV Ratio",
        "Confidence Score", "Snapshot Path", "Staff Acknowledged"
    ])

    for v in violations:
        c_id = v.get("camera_id", "")
        c_name = cam_map.get(c_id, c_id)
        label = v.get("label", "")
        cat = "Pest" if label in PESTS else "Hygiene"
        writer.writerow([
            v.get("id"),
            c_id,
            c_name,
            label,
            cat,
            v.get("timestamp"),
            "Yes" if v.get("amfv_verified") else "No",
            v.get("amfv_ratio"),
            v.get("confidence"),
            v.get("snapshot_path"),
            "Yes" if v.get("acknowledged") else "No",
        ])

    filename = f"hotel_violations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Time-Series Analytics API ────────────────────────────────────────

@app.get("/analytics")
def get_analytics(camera_id: Optional[str] = None):
    """Detailed time-series and categorical violation analytics."""
    data = db.get_analytics(camera_id=camera_id)
    return JSONResponse(content=data)


# ── Evidence Snapshot Gallery API ───────────────────────────────────

@app.get("/snapshots_list")
def get_snapshots_list(camera_id: Optional[str] = None, label: Optional[str] = None, limit: int = 60):
    """Retrieve captured snapshots for the evidence gallery."""
    violations = db.get_violations(camera_id=camera_id, label=label, limit=limit)
    cam_map = {c["id"]: c["name"] for c in db.list_cameras()}

    items = []
    for v in violations:
        path = v.get("snapshot_path", "")
        if path and os.path.exists(path):
            c_id = v.get("camera_id", "")
            items.append({
                "id": v["id"],
                "filename": os.path.basename(path),
                "url": f"/snapshots/{os.path.basename(path)}",
                "label": v["label"],
                "category": "pest" if v["label"] in PESTS else "hygiene",
                "camera_name": cam_map.get(c_id, c_id),
                "timestamp": v["timestamp"],
                "confidence": v.get("confidence", 0.0),
                "acknowledged": bool(v.get("acknowledged", 0)),
            })
    return JSONResponse(content=items)


# ── Dynamic System Settings API ──────────────────────────────────────

@app.get("/settings")
def get_settings():
    """Retrieve current system configuration."""
    saved = db.get_all_settings()
    return JSONResponse(content={
        "amfv_window": int(saved.get("amfv_window", 2)),
        "amfv_threshold_pest": float(saved.get("amfv_threshold_pest", 0.2)),
        "amfv_threshold_hygiene": float(saved.get("amfv_threshold_hygiene", 0.4)),
        "cooldown_seconds": int(saved.get("cooldown_seconds", 30)),
        "notification_email": saved.get("notification_email", RECEIVER_EMAIL),
        "webhook_url": saved.get("webhook_url", ""),
        "email_alerts_enabled": saved.get("email_alerts_enabled", "1") == "1",
    })


@app.post("/settings")
async def update_settings(payload: Dict[str, Any] = Body(...)):
    """Update system settings and propagate to active streams."""
    if "amfv_window" in payload:
        db.set_setting("amfv_window", str(payload["amfv_window"]))
    if "amfv_threshold_pest" in payload:
        db.set_setting("amfv_threshold_pest", str(payload["amfv_threshold_pest"]))
    if "amfv_threshold_hygiene" in payload:
        db.set_setting("amfv_threshold_hygiene", str(payload["amfv_threshold_hygiene"]))
    if "cooldown_seconds" in payload:
        db.set_setting("cooldown_seconds", str(payload["cooldown_seconds"]))
    if "notification_email" in payload:
        db.set_setting("notification_email", str(payload["notification_email"]).strip())
    if "webhook_url" in payload:
        db.set_setting("webhook_url", str(payload["webhook_url"]).strip())
    if "email_alerts_enabled" in payload:
        db.set_setting("email_alerts_enabled", "1" if payload["email_alerts_enabled"] else "0")

    # Propagate to running camera streams
    camera_manager.update_all_configs(
        window_size=int(payload.get("amfv_window")) if "amfv_window" in payload and payload.get("amfv_window") else None,
        threshold_pest=float(payload.get("amfv_threshold_pest")) if "amfv_threshold_pest" in payload and payload.get("amfv_threshold_pest") else None,
        threshold_hygiene=float(payload.get("amfv_threshold_hygiene")) if "amfv_threshold_hygiene" in payload and payload.get("amfv_threshold_hygiene") else None,
        cooldown=int(payload.get("cooldown_seconds")) if "cooldown_seconds" in payload and payload.get("cooldown_seconds") else None,
    )

    return JSONResponse(content={"status": "saved", "message": "Settings updated successfully."})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
