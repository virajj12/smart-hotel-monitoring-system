# OpenCode Parallel Task: Enterprise Alert Dispatcher & Anti-Spam Notification Hub

**Target File**: `D:\Projects\Smart-hotel-monitoring-system\utils\alert_dispatcher.py`  
**Dependencies**: Standard Python Library (`smtplib`, `email.mime`, `urllib.request`, `threading`, `time`, `json`) — **No external pip packages needed!**  
**Collision Rule**: **ZERO-COLLISION**. Do NOT edit `edge_sync.py`, `database.py`, `main.py`, `frontend/`, or any file in `SHMS_central_server/`.

---

## 🎯 Objective

In commercial hotel kitchens, continuous AI surveillance creates serious notification problems:
1. **Alert Flooding / Email Storms**: If a rat or missing apron appears across 30 consecutive frames, naive alerting fires 30 individual emails and webhooks in 2 seconds, blacklisting the sender SMTP server.
2. **Plain-Text Raw Emails**: Basic email notifications look like spam and lack professional hotel branding, severity tags, or responsive layouts.
3. **Fragile Webhooks**: Lack of multi-platform payload adapters (Slack, Discord, Telegram, and standard JSON).

Create a high-speed, thread-safe notification hub (`utils/alert_dispatcher.py`) featuring:
* An **in-memory sliding cooldown anti-spam filter** (debounces duplicate alerts per camera and class).
* An **Executive HTML Email Builder** with embedded base64 evidence snapshot thumbnails and alert severity badges.
* Multi-platform webhook adapters (Generic Webhook, Slack Blocks, Discord Embed, Telegram Bot).

---

## 📐 Detailed Functional Specification

### 1. Function & Class Signatures

```python
class AlertRateLimiter:
    """
    Thread-safe in-memory cooldown filter.
    Prevents alert storms by suppressing identical alerts from the same camera
    within a configurable cooldown window.
    """
    def __init__(self, default_cooldown_seconds: int = 60):
        ...

    def should_dispatch(self, camera_id: str, violation_label: str) -> bool:
        """
        Returns True if the alert is eligible for dispatch.
        Returns False if the alert is throttled by the cooldown window.
        """

class NotificationHub:
    """
    Central dispatcher for email and multi-channel webhook notifications.
    All dispatch calls run asynchronously in daemon worker threads.
    """
    def __init__(self, smtp_config: dict | None = None, webhook_url: str | None = None):
        ...

    def dispatch_violation_alert(
        self,
        event_data: dict,
        snapshot_path: str | None = None,
        channels: list[str] = ["email", "webhook"],
    ) -> dict:
        """
        Processes and dispatches an alert across enabled channels.
        Returns dispatch status summary.
        """
```

---

### 2. Expected `event_data` Input Dictionary

```python
{
    "hotel_name": "Grand Palace Hotel & Suites",
    "location": "Main Kitchen - Prep Counter",
    "camera_id": "cam_01",
    "camera_name": "Prep Station CCTV",
    "label": "no_apron",
    "category": "hygiene",          # 'pest' or 'hygiene'
    "confidence": 0.88,
    "amfv_ratio": 0.50,
    "timestamp": "2026-11-14 13:45:00",
    "incident_id": 1042
}
```

---

### 3. Key Feature Specifications

#### A. Smart Anti-Spam Rate Limiting
* Tracks timestamps with a composite key: `f"{camera_id}:{violation_label}"`.
* If a `cockroach` alert was dispatched on `cam_01` at `13:40:00`, any subsequent `cockroach` alert on `cam_01` before `13:41:00` is dropped.
* However, a different violation (e.g. `no_hairnet`) on `cam_01` or a `cockroach` on `cam_02` will dispatch immediately.

#### B. Industrial Responsive HTML Email Template
* Dark industrial header (`#18181c` background, pure white title).
* Severity Badges:
  * **Pest Alert**: `#dc2626` Crimson pill (`[CRITICAL] PEST DETECTED: RAT`).
  * **Hygiene Alert**: `#d97706` Amber pill (`[HYGIENE BREACH] MISSING HAIRNET`).
* Two-column KPI grid:
  * Camera Name & Location
  * YOLO Confidence % & AMFV Verified %
  * Exact Timestamp & Incident ID
* **Inline Image Attachment (`CID`)**:
  * If `snapshot_path` is provided, attach the image as an inline MIME attachment (`<img src="cid:evidence_snapshot">`) so it renders directly in Outlook, Gmail, and Apple Mail without requiring external image hosting.

#### C. Multi-Webhook Formatter
Detects destination platform from the webhook URL and formats payload automatically:
1. **Slack**: Block Kit JSON with section blocks and markdown text.
2. **Discord**: Discord Embed JSON with color code (Crimson: `14423100`, Amber: `14251782`).
3. **Telegram**: MarkdownV2 text payload (`chat_id`, `text`).
4. **Generic**: Standard SHMS JSON payload.

---

## 🧪 Standalone Verification Block (`if __name__ == "__main__":`)

The module must include a comprehensive test block:

```python
if __name__ == "__main__":
    # 1. Test Rate Limiter
    limiter = AlertRateLimiter(default_cooldown_seconds=2)
    assert limiter.should_dispatch("cam_1", "rat") is True
    assert limiter.should_dispatch("cam_1", "rat") is False  # Throttled!
    assert limiter.should_dispatch("cam_1", "no_apron") is True  # Different class allowed
    assert limiter.should_dispatch("cam_2", "rat") is True  # Different camera allowed
    time.sleep(2.1)
    assert limiter.should_dispatch("cam_1", "rat") is True  # Cooldown expired, allowed!

    # 2. Test HTML Email Generation
    sample_event = {
        "hotel_name": "Grand Palace Hotel",
        "location": "Main Kitchen",
        "camera_id": "cam_01",
        "camera_name": "CCTV Bay 1",
        "label": "cockroach",
        "category": "pest",
        "confidence": 0.92,
        "amfv_ratio": 0.60,
        "timestamp": "2026-11-14 13:45:00",
        "incident_id": 991
    }
    html = build_html_alert_email(sample_event)
    assert "Grand Palace Hotel" in html
    assert "COCKROACH" in html
    assert "CRITICAL" in html

    # 3. Test Webhook Formatter
    slack_payload = format_webhook_payload(sample_event, platform="slack")
    assert "blocks" in slack_payload

    discord_payload = format_webhook_payload(sample_event, platform="discord")
    assert "embeds" in discord_payload

    print("✅ All Alert Dispatcher & Anti-Spam tests passed successfully!")
```

---

## 🚀 Execution Command for Verification

```powershell
python utils/alert_dispatcher.py
```
Assert that it exits with code 0 and all tests pass.

