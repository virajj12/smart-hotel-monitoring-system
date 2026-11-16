# OpenCode Parallel Task: AI Camera Health & Tampering / Occlusion Detector

**Target File**: `D:\Projects\Smart-hotel-monitoring-system\utils\camera_health.py`  
**Dependencies**: `opencv-python`, `numpy` (No new pip packages needed)  
**Collision Rule**: **ZERO-COLLISION**. Do NOT edit `edge_sync.py`, `database.py`, `main.py`, `frontend/`, or any file in `SHMS_central_server/`.

---

## 🎯 Objective

In commercial hotel kitchens, CCTV cameras constantly fail due to:
1. **Grease & Steam Vapor**: Lenses get frosted or blurred by cooking oil vapor.
2. **Intentional Tampering**: Kitchen staff placing cloths, tape, or cardboard over cameras.
3. **Severe Lighting Issues**: Kitchen lights turned off or blinding glare from stainless steel cookware.
4. **Frozen Video Feeds**: RTSP/USB stream hangs, showing a stale static image.

Create a high-speed, standalone computer vision diagnostic module (`utils/camera_health.py`) that analyzes video frames in **< 2 milliseconds** and reports camera health metrics.

---

## 📐 Detailed Functional Specification

### 1. Function Signatures

```python
def check_frame_blur(gray: np.ndarray, threshold: float = 65.0) -> tuple[bool, float]:
    """
    Computes image sharpness using Laplacian variance.
    Returns: (is_blurred: bool, blur_score: float)
    Score < threshold implies blurred/frosted/greasy lens.
    """

def check_occlusion_and_tampering(
    gray: np.ndarray,
    std_thresh: float = 18.0,
    edge_thresh: float = 2.0,
) -> tuple[bool, str]:
    """
    Detects if the camera is covered, blocked, or pointed at a blank surface.
    Returns: (is_occluded: bool, reason: str)
    """

def check_illumination(gray: np.ndarray) -> tuple[str, float]:
    """
    Checks brightness levels.
    Returns: (lighting_status: str, mean_brightness: float)
    Status: 'OPTIMAL' | 'TOO_DARK' (< 25) | 'TOO_BRIGHT' (> 230)
    """

def analyze_camera_health(
    frame: np.ndarray,
    prev_frame: np.ndarray | None = None,
) -> dict:
    """
    Runs complete diagnostic check on a single frame.

    Args:
        frame: BGR numpy image array (from OpenCV).
        prev_frame: Optional previous frame to detect frozen video streams.

    Returns:
        Structured health report dictionary.
    """
```

---

### 2. Expected Output Format (`analyze_camera_health`)

```python
{
    "status": "HEALTHY",               # "HEALTHY" | "DEGRADED" | "CRITICAL"
    "issues": [],                      # e.g. ["BLURRED_LENS", "OCCLUDED", "TOO_DARK", "FROZEN_STREAM"]
    "metrics": {
        "sharpness_score": 142.8,       # Float >= 0.0 (Higher = sharper)
        "brightness_score": 118.5,      # Float 0.0 - 255.0
        "contrast_score": 52.3,         # Float standard deviation
        "frame_diff_delta": 14.2        # Float difference from prev frame (null if no prev frame)
    },
    "tamper_detected": False,          # Boolean flag for alerts
    "recommendation": "Camera operating within optimal parameters.",
    "timestamp": "2026-11-14 13:45:00"
}
```

---

### 3. Stateful Monitor Class: `CameraHealthTracker`

To prevent false alarms from temporary movement (e.g., someone briefly walking in front of the lens), implement a lightweight rolling state tracker:

```python
class CameraHealthTracker:
    def __init__(self, camera_id: str, consecutive_anomaly_limit: int = 5):
        """
        Maintains health state across consecutive frames.
        Only raises an alert if an anomaly persists for N consecutive health checks.
        """
        self.camera_id = camera_id
        self.anomaly_limit = consecutive_anomaly_limit
        self.prev_frame = None
        self.consecutive_blur_count = 0
        self.consecutive_occlusion_count = 0
        self.last_status = "HEALTHY"

    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Processes a frame, updates rolling counters, and returns smoothed diagnostics.
        """
```

---

### 4. Mathematical & Algorithmic Rules

1. **Blur Metric**:
   * Convert frame to grayscale: `gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)`.
   * Downscale to max dimension of 640px for microsecond processing: `cv2.resize(gray, ...)`.
   * Compute variance of Laplacian: `cv2.Laplacian(gray, cv2.CV_64F).var()`.
   * Score $< 65.0$ indicates significant lens fog/steam/grease.
2. **Occlusion & Covering Metric**:
   * Standard deviation: `contrast = float(np.std(gray))`.
   * Canny edge density: `edges = cv2.Canny(gray, 50, 150)`. Edge percentage = `np.count_nonzero(edges) / edges.size * 100.0`.
   * If `contrast < 18.0` and `edge_percentage < 0.5%` $\rightarrow$ Lens is covered with cloth, tape, or cardboard (`tamper_detected = True`).
3. **Frozen Feed Detection**:
   * If `prev_frame` is supplied, calculate absolute difference: `diff = np.mean(cv2.absdiff(gray, prev_gray))`.
   * If `diff < 0.05` on a running CCTV feed, the video capture thread is frozen on a stale buffer.
4. **Graceful Fail-Safe**:
   * If `frame is None`, empty, or corrupted, return a clean `"CRITICAL"` dictionary without raising unhandled exceptions.

---

## 🧪 Standalone Verification Block (`if __name__ == "__main__":`)

The script must run self-contained tests demonstrating detection:

```python
if __name__ == "__main__":
    # 1. Normal Sharp Frame
    sharp = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    report_normal = analyze_camera_health(sharp)
    assert report_normal["status"] in ("HEALTHY", "DEGRADED")

    # 2. Blurred Frame (Gaussian blur simulation)
    blurred = cv2.GaussianBlur(sharp, (45, 45), 0)
    report_blur = analyze_camera_health(blurred)
    assert "BLURRED_LENS" in report_blur["issues"]

    # 3. Occluded / Covered Camera (Black cloth simulation)
    covered = np.full((480, 640, 3), 15, dtype=np.uint8)
    report_covered = analyze_camera_health(covered)
    assert report_covered["tamper_detected"] is True
    assert "OCCLUDED" in report_covered["issues"] or "TOO_DARK" in report_covered["issues"]

    # 4. Overexposed Frame (Direct light / reflection)
    overexposed = np.full((480, 640, 3), 250, dtype=np.uint8)
    report_bright = analyze_camera_health(overexposed)
    assert "TOO_BRIGHT" in report_bright["issues"]

    print("✅ All Camera Health & Tampering diagnostics passed successfully!")
```

---

## 🚀 Execution Command for Verification

```powershell
python utils/camera_health.py
```
Assert that it exits with code 0 and prints verification confirmation.

