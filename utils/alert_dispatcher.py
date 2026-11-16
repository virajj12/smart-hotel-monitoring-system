"""
Enterprise alert dispatcher and anti-spam notification hub for Smart Hotel Monitoring.

Continuous AI surveillance produces duplicate violations across consecutive frames.
This module debounces those duplicates with a thread-safe in-memory cooldown filter,
renders branded HTML alert emails with inline evidence snapshots, and adapts the same
violation event into Slack, Discord, Telegram, or generic webhook payloads.

Everything is built on the Python standard library only and every outbound network
call is executed on a daemon worker thread so the detection pipeline never blocks.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import smtplib
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

__all__ = [
    "AlertRateLimiter",
    "NotificationHub",
    "build_html_alert_email",
    "format_webhook_payload",
    "detect_webhook_platform",
]

# ── Brand palette ───────────────────────────────────────────────────────────
_BRAND_DARK = "#18181c"
_BRAND_ZINC = "#71717a"
_BRAND_MUTED = "#a1a1aa"
_CRIMSON = "#dc2626"
_AMBER = "#d97706"
_SURFACE = "#ffffff"
_CANVAS = "#f4f4f5"

# Discord expects decimal color integers (0xDC143C crimson / 0xD97706 amber).
_DISCORD_CRIMSON = 14423100
_DISCORD_AMBER = 14251782

_PEST_LABELS = {"cockroach", "lizard", "rat"}
_EVIDENCE_CID = "evidence_snapshot"

# Telegram MarkdownV2 reserved characters that must be backslash-escaped.
_MARKDOWN_V2_RESERVED = set("_*[]()~`>#+-=|{}.!")


# ── Shared helpers ──────────────────────────────────────────────────────────


def _clean_text(value: Any, fallback: str) -> str:
    """Return a trimmed, ascii-safe string, falling back when empty."""
    if value is None:
        return fallback
    try:
        text = str(value).strip()
    except Exception:
        return fallback
    if not text:
        return fallback
    return text.encode("ascii", "replace").decode("ascii")


def _as_fraction(value: Any) -> float:
    """Normalise a ratio/percentage input into a 0.0-1.0 float."""
    try:
        if value is None:
            return 0.0
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return 0.0
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    if number > 1.0:
        number = number / 100.0 if number <= 100.0 else 1.0
    return max(0.0, min(number, 1.0))


def _humanize_label(label: str) -> str:
    """Convert a machine label such as ``no_apron`` into ``MISSING APRON``."""
    normalized = _clean_text(label, "violation").strip().replace("-", "_").lower()
    if normalized.startswith("no_"):
        normalized = "missing_" + normalized[3:]
    return normalized.replace("_", " ").strip().upper() or "UNKNOWN VIOLATION"


def _resolve_category(event: dict) -> str:
    """Resolve the violation category, inferring it from the label if absent."""
    category = _clean_text(event.get("category"), "").lower()
    if category in ("pest", "hygiene"):
        return category
    label = _clean_text(event.get("label"), "").strip().lower()
    return "pest" if label in _PEST_LABELS else "hygiene"


def _severity_meta(event: dict) -> dict:
    """Build the shared severity presentation metadata for every channel."""
    category = _resolve_category(event)
    class_name = _humanize_label(event.get("label"))
    is_pest = category == "pest"
    if is_pest:
        badge = f"[CRITICAL] PEST DETECTED: {class_name}"
        summary = "Critical pest activity detected inside a food-handling zone."
    else:
        badge = f"[HYGIENE BREACH] {class_name}"
        summary = "Hygiene compliance breach detected on a monitored station."
    return {
        "category": category,
        "class_name": class_name,
        "is_pest": is_pest,
        "badge": badge,
        "severity": "CRITICAL" if is_pest else "WARNING",
        "color": _CRIMSON if is_pest else _AMBER,
        "discord_color": _DISCORD_CRIMSON if is_pest else _DISCORD_AMBER,
        "summary": summary,
    }


def _escape_markdown_v2(text: str) -> str:
    """Escape a value for Telegram MarkdownV2."""
    return "".join(
        f"\\{char}" if char in _MARKDOWN_V2_RESERVED else char for char in str(text)
    )


def _incident_text(event: dict) -> str:
    incident_id = event.get("incident_id")
    if incident_id is None or str(incident_id).strip() == "":
        return "N/A"
    return f"#{incident_id}"


# ── A. Smart anti-spam rate limiting ────────────────────────────────────────


class AlertRateLimiter:
    """
    Thread-safe in-memory cooldown filter.

    Prevents alert storms by suppressing identical alerts from the same camera
    within a configurable cooldown window. A composite ``camera_id:label`` key is
    used so a different violation on the same camera, or the same violation on a
    different camera, always dispatches immediately.
    """

    def __init__(self, default_cooldown_seconds: int = 60):
        try:
            cooldown = int(default_cooldown_seconds)
        except (TypeError, ValueError):
            cooldown = 60
        self.default_cooldown_seconds = max(0, cooldown)
        self._lock = threading.Lock()
        self._last_dispatch: dict[str, float] = {}

    def should_dispatch(
        self,
        camera_id: str,
        violation_label: str,
        cooldown_seconds: int | None = None,
    ) -> bool:
        """
        Return True when the alert is eligible for dispatch.

        Returns False when the alert is throttled by the active cooldown window.
        A successful (eligible) call records the dispatch timestamp.
        """
        camera_key = _clean_text(camera_id, "unknown_camera").lower()
        label_key = _clean_text(violation_label, "unknown_violation").lower()
        key = f"{camera_key}:{label_key}"

        if cooldown_seconds is None:
            cooldown = self.default_cooldown_seconds
        else:
            try:
                cooldown = max(0, int(cooldown_seconds))
            except (TypeError, ValueError):
                cooldown = self.default_cooldown_seconds

        now = time.monotonic()
        with self._lock:
            last = self._last_dispatch.get(key)
            if last is not None and (now - last) < cooldown:
                return False
            self._last_dispatch[key] = now
            if len(self._last_dispatch) > 4096:
                self._prune_locked(now, cooldown)
            return True

    def reset(self, camera_id: str | None = None, violation_label: str | None = None):
        """Clear cooldown state for one key, one camera, or the whole cache."""
        with self._lock:
            if camera_id is None:
                self._last_dispatch.clear()
                return
            camera_key = _clean_text(camera_id, "unknown_camera").lower()
            if violation_label is None:
                prefix = f"{camera_key}:"
                for key in [k for k in self._last_dispatch if k.startswith(prefix)]:
                    self._last_dispatch.pop(key, None)
                return
            label_key = _clean_text(violation_label, "unknown_violation").lower()
            self._last_dispatch.pop(f"{camera_key}:{label_key}", None)

    def _prune_locked(self, now: float, cooldown: int):
        """Drop stale keys while the lock is held (bounded memory growth)."""
        window = max(cooldown, self.default_cooldown_seconds, 1) * 4
        stale = [key for key, ts in self._last_dispatch.items() if now - ts > window]
        for key in stale:
            self._last_dispatch.pop(key, None)


# ── B. Industrial responsive HTML email builder ─────────────────────────────


def build_html_alert_email(event_data: dict, snapshot_path: str | None = None) -> str:
    """
    Render a branded, responsive HTML alert email for a violation event.

    When ``snapshot_path`` is provided an inline ``cid:evidence_snapshot`` image
    block is embedded; the caller must attach the matching image part with that
    Content-ID for it to render inside Outlook, Gmail, and Apple Mail.
    """
    event = event_data if isinstance(event_data, dict) else {}
    meta = _severity_meta(event)

    hotel = _clean_text(event.get("hotel_name"), "Unknown Hotel")
    location = _clean_text(event.get("location"), "Unassigned Location")
    camera_name = _clean_text(event.get("camera_name"), _clean_text(event.get("camera_id"), "Unknown Camera"))
    timestamp = _clean_text(event.get("timestamp"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    confidence_pct = f"{int(round(_as_fraction(event.get('confidence')) * 100))}%"
    amfv_pct = f"{int(round(_as_fraction(event.get('amfv_ratio')) * 100))}%"
    incident_text = _incident_text(event)

    def kpi(label_text: str, value_text: str, last: bool = False) -> str:
        border = "" if last else "border-bottom:1px solid #e4e4e7;"
        return (
            f'<td width="50%" valign="top" style="padding:14px 18px;{border}'
            'border-right:1px solid #e4e4e7;">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:1.2px;'
            f'text-transform:uppercase;color:{_BRAND_MUTED};">{html.escape(label_text)}</div>'
            f'<div style="font-size:15px;font-weight:600;color:{_BRAND_DARK};'
            f'margin-top:6px;word-break:break-word;">{html.escape(value_text)}</div>'
            "</td>"
        )

    def kpi_right(label_text: str, value_text: str, last: bool = False) -> str:
        border = "" if last else "border-bottom:1px solid #e4e4e7;"
        return (
            f'<td width="50%" valign="top" style="padding:14px 18px;{border}">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:1.2px;'
            f'text-transform:uppercase;color:{_BRAND_MUTED};">{html.escape(label_text)}</div>'
            f'<div style="font-size:15px;font-weight:600;color:{_BRAND_DARK};'
            f'margin-top:6px;word-break:break-word;">{html.escape(value_text)}</div>'
            "</td>"
        )

    image_block = ""
    if snapshot_path and str(snapshot_path).strip():
        image_block = (
            '<tr><td style="padding:8px 32px 0;">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:1.2px;'
            f'text-transform:uppercase;color:{_BRAND_MUTED};margin-bottom:10px;">'
            "Evidence Snapshot</div>"
            '<div style="border:1px solid #e4e4e7;border-radius:10px;overflow:hidden;'
            'background:#0b0b0d;">'
            f'<img src="cid:{_EVIDENCE_CID}" alt="Violation evidence snapshot" '
            'width="576" style="display:block;width:100%;max-width:576px;height:auto;" />'
            "</div></td></tr>"
        )

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
        f"<title>{html.escape(meta['severity'])} {html.escape(meta['class_name'])}</title>"
        "</head>"
        f'<body style="margin:0;padding:0;background-color:{_CANVAS};'
        "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;\">"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background-color:{_CANVAS};padding:24px 0;">'
        '<tr><td align="center">'
        '<table role="presentation" width="640" cellpadding="0" cellspacing="0" '
        'style="width:640px;max-width:640px;background:#ffffff;border-radius:14px;'
        'overflow:hidden;box-shadow:0 12px 32px rgba(24,24,28,0.12);">'
        # Dark industrial header
        '<tr><td style="background-color:#18181c;padding:28px 32px;">'
        f'<div style="color:#ffffff;font-size:21px;font-weight:800;letter-spacing:0.3px;">'
        f"{html.escape(hotel)}</div>"
        f'<div style="color:{_BRAND_MUTED};font-size:11px;margin-top:8px;'
        'letter-spacing:2px;text-transform:uppercase;">'
        "Smart Hotel Monitoring &bull; Security Operations</div>"
        "</td></tr>"
        # Severity badge
        '<tr><td style="padding:28px 32px 0;">'
        f'<span style="display:inline-block;background-color:{meta["color"]};color:#ffffff;'
        'font-size:12px;font-weight:800;letter-spacing:0.6px;padding:9px 16px;'
        f'border-radius:999px;">{html.escape(meta["badge"])}</span>'
        "</td></tr>"
        # Title + summary
        '<tr><td style="padding:16px 32px 0;">'
        f'<div style="font-size:26px;font-weight:800;color:{_BRAND_DARK};line-height:1.2;">'
        f"{html.escape(meta['class_name'])}</div>"
        f'<div style="font-size:14px;color:{_BRAND_ZINC};margin-top:8px;line-height:1.5;">'
        f"{html.escape(meta['summary'])}</div>"
        "</td></tr>"
        # Two-column KPI grid
        '<tr><td style="padding:22px 32px 8px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #e4e4e7;border-radius:10px;overflow:hidden;'
        'border-collapse:separate;border-spacing:0;">'
        "<tr>"
        + kpi("Camera", camera_name)
        + kpi_right("Location", location)
        + "</tr>"
        "<tr>"
        + kpi("YOLO Confidence", confidence_pct)
        + kpi_right("AMFV Verified", amfv_pct)
        + "</tr>"
        "<tr>"
        + kpi("Detected At", timestamp, last=True)
        + kpi_right("Incident ID", incident_text, last=True)
        + "</tr>"
        "</table></td></tr>"
        + image_block
        # Footer
        + '<tr><td style="padding:24px 32px 30px;">'
        f'<div style="border-top:1px solid #e4e4e7;padding-top:18px;font-size:12px;'
        f'color:{_BRAND_MUTED};line-height:1.6;">'
        "This is an automated compliance alert generated by the Smart Hotel "
        "Monitoring System. Snapshot evidence has been forensically watermarked "
        "and retained for audit purposes.</div>"
        f'<div style="margin-top:12px;font-size:11px;color:{_BRAND_MUTED};'
        'letter-spacing:0.4px;">SHMS &bull; Edge AI Node &bull; '
        f"{html.escape(timestamp)}</div>"
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )


# ── C. Multi-webhook formatter ──────────────────────────────────────────────


def detect_webhook_platform(webhook_url: str) -> str:
    """Infer the destination platform from a webhook URL."""
    url = _clean_text(webhook_url, "").lower()
    if "hooks.slack.com" in url or "slack.com/services" in url:
        return "slack"
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return "discord"
    if "api.telegram.org" in url or "t.me/" in url:
        return "telegram"
    return "generic"


def format_webhook_payload(event_data: dict, platform: str = "generic") -> dict:
    """
    Adapt a violation event into a platform-specific webhook payload.

    Supported platforms: ``slack`` (Block Kit), ``discord`` (Embed),
    ``telegram`` (MarkdownV2), and ``generic`` (standard SHMS JSON).
    """
    event = event_data if isinstance(event_data, dict) else {}
    meta = _severity_meta(event)
    resolved = _clean_text(platform, "generic").lower()
    if resolved in ("auto", ""):
        resolved = "generic"

    hotel = _clean_text(event.get("hotel_name"), "Unknown Hotel")
    location = _clean_text(event.get("location"), "Unassigned Location")
    camera_id = _clean_text(event.get("camera_id"), "unknown")
    camera_name = _clean_text(event.get("camera_name"), camera_id)
    timestamp = _clean_text(event.get("timestamp"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    confidence = round(_as_fraction(event.get("confidence")), 4)
    amfv = round(_as_fraction(event.get("amfv_ratio")), 4)
    incident_text = _incident_text(event)

    if resolved == "slack":
        emoji = "\U0001f6a8" if meta["is_pest"] else "\u26a0\ufe0f"
        return {
            "text": f"{meta['badge']} \u2014 {camera_name} ({hotel})",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {meta['badge']}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Hotel:*\n{hotel}"},
                        {"type": "mrkdwn", "text": f"*Location:*\n{location}"},
                        {"type": "mrkdwn", "text": f"*Camera:*\n{camera_name} ({camera_id})"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{meta['severity']}"},
                        {"type": "mrkdwn", "text": f"*YOLO Confidence:*\n{int(round(confidence * 100))}%"},
                        {"type": "mrkdwn", "text": f"*AMFV Verified:*\n{int(round(amfv * 100))}%"},
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Incident {incident_text} \u2022 {timestamp}"}
                    ],
                },
            ],
        }

    if resolved == "discord":
        return {
            "content": f"{meta['badge']} \u2014 {camera_name}",
            "embeds": [
                {
                    "title": f"{meta['badge']}",
                    "description": meta["summary"],
                    "color": meta["discord_color"],
                    "fields": [
                        {"name": "Hotel", "value": hotel, "inline": True},
                        {"name": "Location", "value": location, "inline": True},
                        {"name": "Camera", "value": f"{camera_name} ({camera_id})", "inline": True},
                        {"name": "YOLO Confidence", "value": f"{int(round(confidence * 100))}%", "inline": True},
                        {"name": "AMFV Verified", "value": f"{int(round(amfv * 100))}%", "inline": True},
                        {"name": "Severity", "value": meta["severity"], "inline": True},
                    ],
                    "footer": {"text": f"SHMS \u2022 Incident {incident_text}"},
                    "timestamp": timestamp,
                }
            ],
        }

    if resolved == "telegram":
        chat_id = event.get("chat_id") or event.get("telegram_chat_id") or ""
        lines = [
            f"*{_escape_markdown_v2(meta['badge'])}*",
            "",
            f"*Hotel:* {_escape_markdown_v2(hotel)}",
            f"*Location:* {_escape_markdown_v2(location)}",
            f"*Camera:* {_escape_markdown_v2(camera_name)} ({_escape_markdown_v2(camera_id)})",
            f"*Confidence:* {_escape_markdown_v2(str(int(round(confidence * 100))) + '%')}",
            f"*AMFV:* {_escape_markdown_v2(str(int(round(amfv * 100))) + '%')}",
            f"*Severity:* {_escape_markdown_v2(meta['severity'])}",
            "",
            f"_{_escape_markdown_v2('Incident ' + incident_text + ' • ' + timestamp)}_",
        ]
        return {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "MarkdownV2",
        }

    return {
        "event": "violation_detected",
        "incident_id": event.get("incident_id"),
        "hotel_name": hotel,
        "location": location,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "label": _clean_text(event.get("label"), "violation"),
        "category": meta["category"],
        "severity": meta["severity"],
        "confidence": confidence,
        "amfv_ratio": amfv,
        "timestamp": timestamp,
        "badge": meta["badge"],
    }


# ── Notification hub ────────────────────────────────────────────────────────


class NotificationHub:
    """
    Central dispatcher for email and multi-channel webhook notifications.

    All dispatch calls run asynchronously in daemon worker threads, guarded by an
    :class:`AlertRateLimiter` so repeated detections collapse into a single alert.
    """

    DEFAULT_SMTP = {
        "host": "smtp.gmail.com",
        "port": 465,
        "use_ssl": True,
        "sender": "",
        "sender_name": "SHMS Alert Bot",
        "password": "",
        "recipient": "",
    }

    def __init__(self, smtp_config: dict | None = None, webhook_url: str | None = None):
        merged = dict(self.DEFAULT_SMTP)
        if isinstance(smtp_config, dict):
            merged.update({k: v for k, v in smtp_config.items() if v is not None})
        self.smtp_config = merged
        self.webhook_url = _clean_text(webhook_url, "")
        self.rate_limiter = AlertRateLimiter(default_cooldown_seconds=60)
        self._threads: list[threading.Thread] = []
        self._threads_lock = threading.Lock()

    # -- Public API ---------------------------------------------------------

    def dispatch_violation_alert(
        self,
        event_data: dict,
        snapshot_path: str | None = None,
        channels: list[str] | None = None,
    ) -> dict:
        """
        Process and dispatch an alert across enabled channels.

        Returns a dispatch status summary. The actual email/webhook delivery runs
        on daemon threads, so this call returns as soon as the alert is queued.
        """
        event = dict(event_data) if isinstance(event_data, dict) else {}
        camera_id = _clean_text(event.get("camera_id"), "unknown_camera")
        label = _clean_text(event.get("label"), "violation")
        meta = _severity_meta(event)

        if isinstance(channels, str):
            requested = [channels]
        elif channels is None:
            requested = ["email", "webhook"]
        else:
            requested = [str(c).lower() for c in channels if c is not None]
        requested = [c for c in requested if c]

        active = []
        for channel in requested:
            if channel == "email" and self._email_enabled():
                active.append("email")
            elif channel == "webhook" and self.webhook_url:
                active.append("webhook")
        active = list(dict.fromkeys(active))

        base = {
            "camera_id": camera_id,
            "label": label,
            "category": meta["category"],
            "severity": meta["severity"],
            "incident_id": event.get("incident_id"),
            "requested_channels": requested,
            "queued_at": datetime.now().isoformat(timespec="seconds"),
            "cooldown_seconds": self.rate_limiter.default_cooldown_seconds,
        }

        if not active:
            return {
                **base,
                "status": "skipped",
                "throttled": False,
                "channels": [],
                "dispatched_channels": [],
                "message": "No notification channels are configured",
            }

        if not self.rate_limiter.should_dispatch(camera_id, label):
            return {
                **base,
                "status": "throttled",
                "throttled": True,
                "channels": active,
                "dispatched_channels": [],
                "message": f"Duplicate '{label}' alert on '{camera_id}' suppressed by cooldown",
            }

        for channel in active:
            if channel == "email":
                self._spawn(self._send_email, event, snapshot_path, name=f"alert-email-{camera_id}")
            else:
                self._spawn(self._send_webhook, event, name=f"alert-webhook-{camera_id}")

        return {
            **base,
            "status": "dispatched",
            "throttled": False,
            "channels": active,
            "dispatched_channels": active,
            "message": f"Alert queued for {', '.join(active)}",
        }

    def shutdown(self, timeout: float = 5.0):
        """Best-effort join of in-flight notification workers."""
        with self._threads_lock:
            threads = list(self._threads)
            self._threads.clear()
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=timeout)

    # -- Internals ----------------------------------------------------------

    def _email_enabled(self) -> bool:
        return bool(self.smtp_config.get("sender") and self.smtp_config.get("recipient"))

    def _spawn(self, target, *args, name: str = "alert-worker", **kwargs):
        thread = threading.Thread(target=target, args=args, kwargs=kwargs, name=name, daemon=True)
        with self._threads_lock:
            self._threads = [t for t in self._threads if t.is_alive()]
            self._threads.append(thread)
        thread.start()
        return thread

    def _send_email(self, event: dict, snapshot_path: str | None) -> bool:
        cfg = self.smtp_config
        sender = cfg.get("sender")
        recipient = cfg.get("recipient")
        password = cfg.get("password")
        if not sender or not recipient:
            return False

        try:
            message = self._build_email_message(event, snapshot_path)
        except Exception as exc:
            print(f"[Alert Dispatcher] Failed to build alert email: {exc}")
            return False

        host = _clean_text(cfg.get("host"), "smtp.gmail.com")
        try:
            port = int(cfg.get("port", 465))
        except (TypeError, ValueError):
            port = 465
        use_ssl = bool(cfg.get("use_ssl", True))

        try:
            if use_ssl:
                try:
                    with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                        if password:
                            smtp.login(sender, password)
                        smtp.send_message(message)
                    print(f"[Alert Dispatcher] Alert email sent to {recipient}")
                    return True
                except Exception:
                    with smtplib.SMTP(host, 587, timeout=15) as smtp:
                        smtp.starttls()
                        if password:
                            smtp.login(sender, password)
                        smtp.send_message(message)
                    print(f"[Alert Dispatcher] Alert email sent via STARTTLS to {recipient}")
                    return True
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls()
                if password:
                    smtp.login(sender, password)
                smtp.send_message(message)
            print(f"[Alert Dispatcher] Alert email sent to {recipient}")
            return True
        except Exception as exc:
            print(f"[Alert Dispatcher] Failed to send alert email: {exc}")
            return False

    def _build_email_message(self, event: dict, snapshot_path: str | None) -> MIMEMultipart:
        cfg = self.smtp_config
        sender = cfg.get("sender")
        recipient = cfg.get("recipient")
        meta = _severity_meta(event)
        hotel = _clean_text(event.get("hotel_name"), "Unknown Hotel")
        camera_name = _clean_text(event.get("camera_name"), _clean_text(event.get("camera_id"), "Camera"))

        message = MIMEMultipart("related")
        message["Subject"] = f"[{meta['severity']}] {meta['badge']} - {camera_name} ({hotel})"
        message["From"] = formataddr((_clean_text(cfg.get("sender_name"), "SHMS Alert Bot"), sender))
        message["To"] = recipient

        message.attach(MIMEText(build_html_alert_email(event, snapshot_path), "html", "utf-8"))

        if snapshot_path and str(snapshot_path).strip():
            try:
                with open(snapshot_path, "rb") as handle:
                    raw = handle.read()
                if raw:
                    image = MIMEImage(raw)
                    image.add_header("Content-ID", f"<{_EVIDENCE_CID}>")
                    image.add_header("Content-Disposition", "inline", filename=os.path.basename(snapshot_path))
                    message.attach(image)
            except OSError as exc:
                print(f"[Alert Dispatcher] Snapshot attachment skipped: {exc}")

        return message

    def _send_webhook(self, event: dict) -> bool:
        url = self.webhook_url
        if not url:
            return False
        platform = detect_webhook_platform(url)
        payload = format_webhook_payload(event, platform=platform)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SHMS-AlertDispatcher/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                print(f"[Alert Dispatcher] Webhook ({platform}) delivered ({response.status})")
                return True
        except urllib.error.HTTPError as exc:
            print(f"[Alert Dispatcher] Webhook ({platform}) HTTP {exc.code}: {exc.reason}")
        except urllib.error.URLError as exc:
            print(f"[Alert Dispatcher] Webhook ({platform}) unreachable: {exc.reason}")
        except Exception as exc:
            print(f"[Alert Dispatcher] Webhook ({platform}) failed: {exc}")
        return False


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
        "incident_id": 991,
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

    # 4. Test platform detection + generic payload
    assert detect_webhook_platform("https://hooks.slack.com/services/T00/B00/xxx") == "slack"
    assert detect_webhook_platform("https://discord.com/api/webhooks/123/abc") == "discord"
    assert detect_webhook_platform("https://api.telegram.org/bot123/sendMessage") == "telegram"
    assert detect_webhook_platform("https://example.com/hook") == "generic"

    generic_payload = format_webhook_payload(sample_event, platform="generic")
    assert generic_payload["event"] == "violation_detected"
    assert generic_payload["category"] == "pest"

    telegram_payload = format_webhook_payload(sample_event, platform="telegram")
    assert telegram_payload["parse_mode"] == "MarkdownV2"

    # 5. Test hub skips when no channel is configured (no network touched)
    hub = NotificationHub()
    skipped = hub.dispatch_violation_alert(sample_event, channels=[])
    assert skipped["status"] == "skipped"
    assert skipped["throttled"] is False

    print("\u2705 All Alert Dispatcher & Anti-Spam tests passed successfully!")
