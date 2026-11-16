# OpenCode Parallel Implementation Tasks

This document contains complete, self-contained specifications for **Task 1 (Forensic Snapshot Watermarking)** and **Task 2 (Executive PDF Compliance Report Generator)**.

---

## ⚠️ Global Rules for OpenCode
1. **Zero Collision**: Do NOT modify `edge_sync.py`, `database.py` sync logic, or any WebSocket connections.
2. **Self-Contained**: Each module must contain its own test block under `if __name__ == "__main__":` so it can be executed and verified standalone.
3. **Robustness**: Functions must handle missing or null fields gracefully with fallbacks and never raise unhandled exceptions during surveillance loops.

---

# 📦 TASK 1: Forensic Snapshot Watermarking Utility

* **Target File**: `D:\Projects\Smart-hotel-monitoring-system\utils\watermark.py`
* **Dependencies**: `opencv-python`, `numpy`, `hashlib`

### 🎯 Objective
Create a standalone image processing module that burns a forensic, tamper-evident Heads-Up Display (HUD) banner onto captured violation snapshot frames.

### 📐 Functional Specification

#### 1. Function Signatures
```python
def apply_forensic_watermark(
    frame: np.ndarray,
    metadata: dict,
    position: str = "bottom",
) -> np.ndarray:
    """
    Applies a semi-transparent HUD banner with violation details onto a frame.
    
    Args:
        frame: BGR image numpy array (cv2 image).
        metadata: Dictionary containing violation details.
        position: 'bottom' (default) or 'top'.
        
    Returns:
        Watermarked BGR image numpy array.
    """

def save_watermarked_snapshot(
    frame: np.ndarray,
    output_path: str,
    metadata: dict,
    quality: int = 92,
) -> str:
    """
    Applies forensic watermark and saves the image to output_path.
    Returns the absolute path of the saved image.
    """
```

#### 2. Expected `metadata` Dictionary Fields
```python
{
    "hotel_name": "Grand Palace Hotel",
    "location": "Main Kitchen - Prep Counter",
    "camera_name": "Kitchen CCTV 1",
    "label": "no_apron",            # Class name
    "category": "hygiene",          # 'pest' or 'hygiene'
    "confidence": 0.88,             # Float 0.0 - 1.0
    "amfv_ratio": 0.50,             # Float 0.0 - 1.0
    "timestamp": "2026-11-13 18:30:00",
}
```

#### 3. Visual & Aesthetic Requirements
* **Theme**: Match the project's carbon/ash-grey theme:
  * Dark banner background (`#101014` with ~75% opacity blended using `cv2.addWeighted`).
  * Pure white primary text for violation title.
  * Zinc-400 (`#a1a1aa`) for secondary metadata labels.
* **Category Badge Color**:
  * If `category == 'pest'`: Alert Crimson background (`BGR: (30, 30, 220)`).
  * If `category == 'hygiene'`: Amber background (`BGR: (20, 160, 240)`).
* **Text Contents on HUD**:
  * **Line 1 (Bold)**: Category Badge + Class Name (e.g. `[PPE BREACH] MISSING APRON`) &bull; `AMFV Verified: 50%` &bull; `Conf: 88%`
  * **Line 2 (Small)**: `Grand Palace Hotel | Main Kitchen - Prep Counter | 2026-11-13 18:30:00`
  * **Line 3 (Mono font)**: `SHA256 Fingerprint: <first 16 hex chars of frame hash>` (Proves snapshot authenticity).

#### 4. Verification Block (`if __name__ == "__main__":`)
Create a black/dummy image (`640x480x3`), apply the watermark, write it to `test_watermark.jpg`, and print verification confirmation.

---

# 📦 TASK 2: Executive PDF Compliance Report Generator

* **Target File**: `D:\Projects\SHMS_central_server\utils\pdf_report.py`
* **Dependencies**: `reportlab` (`pip install reportlab`)

### 🎯 Objective
Generate a printable, 1-page **Food Safety & Kitchen Hygiene Audit Certificate / Executive Compliance PDF** for hotel management and municipal food safety inspectors.

### 📐 Functional Specification

#### 1. Function Signature
```python
def generate_compliance_pdf(
    report_data: dict,
    output_path: str = "compliance_report.pdf",
) -> str:
    """
    Generates a formal 1-page executive PDF compliance certificate.
    
    Args:
        report_data: Dictionary containing fleet audit metrics.
        output_path: Destination filepath for the generated PDF.
        
    Returns:
        Absolute path to the generated PDF document.
    """
```

#### 2. Expected `report_data` Dictionary Fields
```python
{
    "report_id": "AUDIT-2026-NYC-0092",
    "hotel_name": "Grand Palace Hotel & Suites",
    "location": "Main Kitchen & Food Prep Facility",
    "audit_period": "Nov 06, 2026 - Nov 13, 2026",
    "generated_at": "2026-11-13 18:30:00",
    "total_camera_hours": 336.5,
    "total_violations": 14,
    "pest_incursions": 1,
    "hygiene_breaches": 13,
    "compliance_score": 93.5,       # Percentage 0 - 100
    "stations_breakdown": [
        {"station": "Food Prep Counter", "cameras": 2, "pests": 0, "hygiene": 8, "status": "Compliant"},
        {"station": "Dishwashing & Sanitizing", "cameras": 1, "pests": 1, "hygiene": 3, "status": "Caution"},
        {"station": "Cold Storage & Pantry", "cameras": 1, "pests": 0, "hygiene": 2, "status": "Compliant"},
    ],
    "inspector_notes": "All kitchen personnel complied with hairnet and glove regulations. One minor apron infraction resolved immediately."
}
```

#### 3. Visual & Layout Requirements
* **Page Layout**: Exactly 1 page, Letter / A4 portrait, professional margins (0.5 to 0.75 in).
* **Color Palette**:
  * Primary Accent: Deep Navy / Slate `#1e293b`.
  * Highlight Accent: Emerald `#059669` (Grade A), Amber `#d97706` (Grade B), Red `#dc2626` (Grade C).
  * Neutral Dark: `#0f172a`.
* **Required Sections**:
  1. **Header Banner**: "Smart Hotel AI Surveillance — Food Safety Audit Certificate" with Report ID and generation date.
  2. **Hotel & Period Block**: Hotel Name, Branch, and Monitored Hours.
  3. **Compliance Grade Badge**:
     * Score $\ge 90\%$: `GRADE A — EXCELLENT COMPLIANCE` (Green).
     * Score $75\% - 89\%$: `GRADE B — SATISFACTORY` (Amber).
     * Score $< 75\%$: `GRADE C — ACTION REQUIRED` (Red).
  4. **KPI Summary Grid**: 4 columns (Total Violations, Pest Incursions, PPE Breaches, Compliance %).
  5. **Station Breakdown Table**: Neat alternating row colors listing Station Name, Monitored Cameras, Infractions, and Risk Status.
  6. **Formal Sign-off Box**:
     * "Automated AMFV Continuous Surveillance Verification" stamp.
     * Signature and date lines for:
       - Hotel General Manager / Executive Chef
       - Quality & Food Safety Auditor

#### 4. Verification Block (`if __name__ == "__main__":`)
Generate a mock report with the sample data above, output to `sample_compliance_report.pdf`, and assert file creation with size > 1 KB.

