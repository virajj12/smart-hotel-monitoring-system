"""
Multi-camera management with per-camera processing threads.
Each camera runs YOLO inference independently and reports violations via callback.
"""

import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Callable, Dict, Optional

import cv2
import numpy as np


def _mask_url_credentials(url: str) -> str:
    """Mask embedded username:password in URLs."""
    if not url or not isinstance(url, str):
        return ""
    return re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://\1:***@", url)

# ── Constants ────────────────────────────────────────────────────────────
VIOLATIONS = ["cockroach", "lizard", "rat", "no_apron", "no_gloves", "no_hairnet"]
PESTS = ["cockroach", "lizard", "rat"]
DEFAULT_AMFV_WINDOW = 2
DEFAULT_AMFV_THRESHOLD_PEST = 0.2
DEFAULT_AMFV_THRESHOLD_HYGIENE = 0.4

# Shared lock to serialize YOLO inference across concurrent camera threads
_MODEL_INFERENCE_LOCK = threading.Lock()


class CameraStream:
    """Manages a single camera's capture, inference, and AMFV state."""

    def __init__(
        self,
        camera_id: str,
        name: str,
        source: str,
        location: str,
        model,
        on_violation: Callable,
        source_type: str = "rtsp",
    ):
        self.camera_id = camera_id
        self.name = name
        self.source = source
        self.location = location
        self.model = model
        self.on_violation = on_violation
        self.source_type = source_type

        # State flags
        self.enabled: bool = False
        self.running: bool = False
        self.connected: bool = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.thread: Optional[threading.Thread] = None

        # Frame buffer (thread-safe)
        self._latest_frame: Optional[np.ndarray] = None
        self._annotated_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # FPS tracking
        self.fps: float = 0.0
        self._fps_window: deque = deque(maxlen=30)
        self.frame_count: int = 0

        # AMFV state & thresholds
        self.amfv_window_size: int = DEFAULT_AMFV_WINDOW
        self.threshold_pest: float = DEFAULT_AMFV_THRESHOLD_PEST
        self.threshold_hygiene: float = DEFAULT_AMFV_THRESHOLD_HYGIENE
        self.amfv_windows: Dict[str, deque] = {v: deque(maxlen=self.amfv_window_size) for v in VIOLATIONS}
        self.amfv_confirmed: set = set()
        self.amfv_ratios: Dict[str, float] = {v: 0.0 for v in VIOLATIONS}

        # Cooldown
        self.cooldown_seconds: int = 30
        self.last_alert_time: Dict[str, float] = {}

        # 4-Tier Detection & Calibration Filters
        self.conf_threshold: float = 0.45
        self.geometric_filter: bool = True
        self.imgsz: int = 640
        self.iou_threshold: float = 0.45
        self.enable_tta: bool = False

        # Reconnection
        self._reconnect_attempts: int = 0
        self._max_reconnect_delay: int = 30

    def update_amfv_config(
        self,
        window_size: Optional[int] = None,
        threshold_pest: Optional[float] = None,
        threshold_hygiene: Optional[float] = None,
        cooldown: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        geometric_filter: Optional[bool] = None,
        imgsz: Optional[int] = None,
        iou_threshold: Optional[float] = None,
        enable_tta: Optional[bool] = None,
    ):
        """Dynamically update AMFV parameters and inference filters."""
        if window_size is not None and window_size > 0:
            self.amfv_window_size = window_size
            for v in VIOLATIONS:
                old_items = list(self.amfv_windows[v])
                self.amfv_windows[v] = deque(old_items, maxlen=window_size)
        if threshold_pest is not None and 0.0 < threshold_pest <= 1.0:
            self.threshold_pest = threshold_pest
        if threshold_hygiene is not None and 0.0 < threshold_hygiene <= 1.0:
            self.threshold_hygiene = threshold_hygiene
        if cooldown is not None and cooldown >= 0:
            self.cooldown_seconds = cooldown
        if conf_threshold is not None and 0.0 < conf_threshold <= 1.0:
            self.conf_threshold = conf_threshold
        if geometric_filter is not None:
            self.geometric_filter = bool(geometric_filter)
        if imgsz is not None and imgsz >= 160:
            self.imgsz = imgsz
        if iou_threshold is not None and 0.0 < iou_threshold <= 1.0:
            self.iou_threshold = iou_threshold
        if enable_tta is not None:
            self.enable_tta = bool(enable_tta)

    def _get_capture_source(self):
        """Return the appropriate capture source value for VideoCapture."""
        if self.source_type == "webcam":
            try:
                return int(self.source)
            except (ValueError, TypeError):
                return 0
        src = str(self.source).strip()
        # Auto-append /video for IP Webcam / HTTP stream endpoints if path omitted
        if self.source_type == "http" and src.startswith("http"):
            import urllib.parse
            parsed = urllib.parse.urlparse(src)
            if not parsed.path or parsed.path == "/":
                src = src.rstrip("/") + "/video"
        return src

    def _connect(self) -> bool:
        """Open VideoCapture and verify we can read a frame."""
        source = self._get_capture_source()
        self.cap = cv2.VideoCapture(source)

        if self.source_type == "rtsp" and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            print(f"[Camera {self.camera_id}] Failed to open source: {source}")
            self.connected = False
            return False

        ret, _ = self.cap.read()
        if not ret:
            print(f"[Camera {self.camera_id}] Opened but failed to read initial frame from: {source}")
            self.connected = False
            return False

        print(f"[Camera {self.camera_id}] Connected to: {source}")
        self.connected = True
        self._reconnect_attempts = 0
        return True

    def _reconnect(self) -> bool:
        """Release old capture and attempt reconnection with exponential backoff."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self.connected = False
        delay = min(2 ** self._reconnect_attempts, self._max_reconnect_delay)
        self._reconnect_attempts += 1
        print(f"[Camera {self.camera_id}] Reconnecting in {delay}s (attempt {self._reconnect_attempts})...")
        time.sleep(delay)
        return self._connect()

    def _get_amfv_threshold(self, label: str) -> float:
        """Return the AMFV threshold for the given violation label."""
        if label in PESTS:
            return self.threshold_pest
        return self.threshold_hygiene

    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Run YOLO inference with Tier 1/2 filters, update AMFV windows, fire callbacks."""
        with _MODEL_INFERENCE_LOCK:
            results = self.model(
                frame,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.imgsz,
                augment=self.enable_tta,
                verbose=False,
            )
            annotated = results[0].plot()

        # Collect detected violations with max confidence per class
        detected: Dict[str, float] = {}
        frame_h, frame_w = frame.shape[:2]
        frame_area = max(1, frame_h * frame_w)

        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            label = self.model.names.get(cls_id, "")
            conf = float(box.conf[0])
            if label not in VIOLATIONS:
                continue

            # Tier 1: Confidence Calibration
            if conf < self.conf_threshold:
                continue

            # Tier 2: Geometric Aspect & Size Ratio Filter (reject wire noise & bounding box glitches)
            if self.geometric_filter and box.xywh is not None and len(box.xywh[0]) >= 4:
                bw = float(box.xywh[0][2])
                bh = float(box.xywh[0][3])
                if bw < 12 or bh < 12:
                    continue  # Microscopic pixel noise
                aspect_ratio = max(bw, bh) / max(1.0, min(bw, bh))
                if aspect_ratio > 7.0:
                    continue  # Extreme slit or wire-like bounding box glitch
                box_area = bw * bh
                if (box_area / frame_area) > 0.95:
                    continue  # Unrealistic whole-frame hallucination

            detected[label] = max(detected.get(label, 0.0), conf)

        # Update AMFV windows for each violation class
        for violation in VIOLATIONS:
            if violation in detected:
                self.amfv_windows[violation].append(1)
            else:
                self.amfv_windows[violation].append(0)

            window = self.amfv_windows[violation]
            if len(window) > 0:
                ratio = sum(window) / len(window)
            else:
                ratio = 0.0
            self.amfv_ratios[violation] = ratio

            threshold = self._get_amfv_threshold(violation)

            if ratio >= threshold and violation not in self.amfv_confirmed:
                # Newly confirmed
                self.amfv_confirmed.add(violation)

                # Check cooldown
                now = time.time()
                last = self.last_alert_time.get(violation, 0)
                if now - last >= self.cooldown_seconds:
                    self.last_alert_time[violation] = now
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    confidence = detected.get(violation, 0.0)
                    self.on_violation(
                        self.camera_id,
                        violation,
                        timestamp,
                        annotated,
                        ratio,
                        confidence,
                    )
            elif ratio < threshold and violation in self.amfv_confirmed:
                self.amfv_confirmed.discard(violation)

        return annotated

    def _run(self):
        """Main loop: connect, read frames, process, handle failures."""
        if not self._connect():
            while self.running:
                if self._reconnect():
                    break

        while self.running:
            if not self.connected or self.cap is None or not self.cap.isOpened():
                if not self._reconnect():
                    continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                if self.source_type == "file":
                    # Loop video files continuously
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if not ret or frame is None:
                        if not self._reconnect():
                            continue
                else:
                    print(f"[Camera {self.camera_id}] Frame read failure, reconnecting...")
                    self.connected = False
                    if not self._reconnect():
                        continue
                    continue

            t0 = time.time()
            try:
                annotated = self._process_frame(frame)
            except Exception as e:
                print(f"[Camera {self.camera_id}] Inference error: {e}")
                annotated = frame.copy()
            elapsed = time.time() - t0
            self._fps_window.append(elapsed)

            if len(self._fps_window) > 0:
                avg = sum(self._fps_window) / len(self._fps_window)
                self.fps = round(1.0 / avg, 1) if avg > 0 else 0.0

            self.frame_count += 1

            with self._frame_lock:
                self._latest_frame = frame
                self._annotated_frame = annotated

        # Cleanup
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.connected = False
        print(f"[Camera {self.camera_id}] Stream stopped.")

    def start(self):
        """Start the camera processing thread."""
        self.running = True
        self.enabled = True
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"cam-{self.camera_id}")
        self.thread.start()

    def stop(self):
        """Stop the camera processing thread."""
        self.running = False
        self.enabled = False
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.connected = False

    def get_frame(self) -> Optional[bytes]:
        """Return the latest annotated frame as JPEG bytes."""
        with self._frame_lock:
            if self._annotated_frame is None:
                return None
            ret, buf = cv2.imencode(".jpg", self._annotated_frame)
            if not ret:
                return None
            return buf.tobytes()

    def get_raw_frame(self) -> Optional[np.ndarray]:
        """Return the latest annotated frame as a numpy array copy."""
        with self._frame_lock:
            if self._annotated_frame is None:
                return None
            return self._annotated_frame.copy()

    def generate_mjpeg(self):
        """Generator yielding MJPEG boundary frames for streaming."""
        while self.running:
            frame_bytes = self.get_frame()
            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
                time.sleep(0.03)
            else:
                time.sleep(0.1)

    def get_status(self) -> dict:
        """Return camera status information with sanitized credentials."""
        return {
            "id": self.camera_id,
            "name": self.name,
            "source": _mask_url_credentials(self.source),
            "location": self.location,
            "source_type": self.source_type,
            "enabled": self.enabled,
            "connected": self.connected,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "running": self.running,
        }

    def get_amfv_status(self) -> dict:
        """Return current AMFV state with active dynamic window size."""
        return {
            "ratios": dict(self.amfv_ratios),
            "confirmed": list(self.amfv_confirmed),
            "thresholds": {v: self._get_amfv_threshold(v) for v in VIOLATIONS},
            "window_size": self.amfv_window_size,
        }

    def reset_amfv(self):
        """Reset all AMFV state and cooldown timers."""
        for v in VIOLATIONS:
            self.amfv_windows[v].clear()
            self.amfv_ratios[v] = 0.0
        self.amfv_confirmed.clear()
        self.last_alert_time.clear()


class CameraManager:
    """Manages all CameraStream instances."""

    def __init__(self, model, on_violation: Callable):
        self.model = model
        self.on_violation = on_violation
        self.cameras: Dict[str, CameraStream] = {}
        self._lock = threading.Lock()

    def add_camera(
        self,
        name: str,
        source: str,
        location: str,
        source_type: str = "rtsp",
        camera_id: Optional[str] = None,
    ) -> CameraStream:
        """Create a new CameraStream, start it, and return it."""
        if camera_id is None:
            camera_id = f"cam_{uuid.uuid4().hex[:8]}"

        stream = CameraStream(
            camera_id=camera_id,
            name=name,
            source=source,
            location=location,
            model=self.model,
            on_violation=self.on_violation,
            source_type=source_type,
        )
        stream.start()

        with self._lock:
            self.cameras[camera_id] = stream

        return stream

    def remove_camera(self, camera_id: str) -> bool:
        """Stop and remove a camera stream."""
        with self._lock:
            stream = self.cameras.pop(camera_id, None)
        if stream is not None:
            stream.stop()
            return True
        return False

    def get_camera(self, camera_id: str) -> Optional[CameraStream]:
        """Return the CameraStream for the given ID, or None."""
        with self._lock:
            return self.cameras.get(camera_id)

    def list_cameras(self) -> list[dict]:
        """Return status dicts for all managed cameras."""
        with self._lock:
            return [stream.get_status() for stream in self.cameras.values()]

    def toggle_camera(self, camera_id: str) -> Optional[bool]:
        """Toggle a camera on/off. Returns the new running state, or None if not found."""
        with self._lock:
            stream = self.cameras.get(camera_id)
        if stream is None:
            return None

        if stream.running:
            stream.stop()
        else:
            stream.start()
        return stream.running

    def stop_all(self):
        """Stop all camera streams."""
        with self._lock:
            streams = list(self.cameras.values())
        for stream in streams:
            stream.stop()

    def update_all_configs(
        self,
        window_size: Optional[int] = None,
        threshold_pest: Optional[float] = None,
        threshold_hygiene: Optional[float] = None,
        cooldown: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        geometric_filter: Optional[bool] = None,
        imgsz: Optional[int] = None,
        iou_threshold: Optional[float] = None,
        enable_tta: Optional[bool] = None,
    ):
        """Update AMFV and YOLO calibration across all active camera streams."""
        with self._lock:
            for stream in self.cameras.values():
                stream.update_amfv_config(
                    window_size=window_size,
                    threshold_pest=threshold_pest,
                    threshold_hygiene=threshold_hygiene,
                    cooldown=cooldown,
                    conf_threshold=conf_threshold,
                    geometric_filter=geometric_filter,
                    imgsz=imgsz,
                    iou_threshold=iou_threshold,
                    enable_tta=enable_tta,
                )

    @staticmethod
    def test_connection(source: str, source_type: str) -> dict:
        """Test a camera connection. Returns {success, resolution, preview, error}."""
        result = {"success": False, "resolution": None, "preview": None, "error": None}
        try:
            if source_type == "webcam":
                try:
                    cap_source = int(source)
                except (ValueError, TypeError):
                    cap_source = 0
            else:
                cap_source = str(source).strip()
                # Validate protocol scheme to prevent arbitrary local socket or file abuse
                if source_type in ("rtsp", "http"):
                    import urllib.parse
                    parsed = urllib.parse.urlparse(cap_source)
                    if parsed.scheme.lower() not in ("rtsp", "rtsps", "http", "https"):
                        return {"success": False, "resolution": None, "preview": None, "error": f"Invalid protocol scheme: {parsed.scheme}"}
                    if source_type == "http" and (not parsed.path or parsed.path == "/"):
                        cap_source = cap_source.rstrip("/") + "/video"
                elif source_type == "file":
                    # Disallow path traversal out of workspace
                    clean_path = os.path.normpath(cap_source)
                    if clean_path.startswith("..") or os.path.isabs(clean_path):
                        if not os.path.exists(clean_path):
                            return {"success": False, "resolution": None, "preview": None, "error": "Invalid file path"}

            cap = cv2.VideoCapture(cap_source)
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000)
            except Exception:
                pass

            if not cap.isOpened():
                result["error"] = "Failed to open video source. Please check the IP, port, and credentials."
                return result

            ret, frame = cap.read()
            if not ret or frame is None:
                result["error"] = "Connected to host, but failed to retrieve frame stream."
                cap.release()
                return result

            h, w = frame.shape[:2]
            result["resolution"] = f"{w}x{h}"
            result["success"] = True

            # Generate base64 preview
            ret_enc, buf = cv2.imencode(".jpg", frame)
            if ret_enc:
                import base64
                result["preview"] = base64.b64encode(buf.tobytes()).decode("utf-8")

            cap.release()
        except Exception as e:
            result["error"] = str(e)

        return result
