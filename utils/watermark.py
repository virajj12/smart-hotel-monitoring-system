"""Forensic HUD watermarking for violation snapshot frames."""

from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime
from typing import Any

import cv2
import numpy as np

_BANNER_BGR = (20, 16, 16)
_BANNER_OPACITY = 0.75
_WHITE = (255, 255, 255)
_ZINC_400 = (170, 161, 161)
_PEST_BGR = (30, 30, 220)
_HYGIENE_BGR = (20, 160, 240)
_PEST_LABELS = {"cockroach", "lizard", "rat"}
_FONT_TITLE = cv2.FONT_HERSHEY_DUPLEX
_FONT_BODY = cv2.FONT_HERSHEY_SIMPLEX
_FONT_MONO = cv2.FONT_HERSHEY_PLAIN


def _clean_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return text.encode("ascii", "replace").decode("ascii")


def _as_fraction(value: Any) -> float:
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
    normalized = label.strip().replace("-", "_").lower()
    if normalized.startswith("no_"):
        normalized = "missing_" + normalized[3:]
    return normalized.replace("_", " ").strip().upper() or "UNKNOWN VIOLATION"


def _fingerprint(frame: np.ndarray) -> str:
    try:
        payload = np.ascontiguousarray(frame).tobytes()
        return hashlib.sha256(payload).hexdigest()[:16].upper()
    except Exception:
        return "0" * 16


def _text_width(text: str, font: int, scale: float, thickness: int) -> int:
    return cv2.getTextSize(text, font, scale, thickness)[0][0]


def _text_height(text: str, font: int, scale: float, thickness: int) -> int:
    return cv2.getTextSize(text, font, scale, thickness)[0][1]


def _fit_scale(
    text: str,
    font: int,
    scale: float,
    thickness: int,
    max_width: int,
    min_scale: float = 0.22,
) -> float:
    while scale > min_scale and _text_width(text, font, scale, thickness) > max_width:
        scale *= 0.94
    return scale


def _truncate(
    text: str,
    font: int,
    scale: float,
    thickness: int,
    max_width: int,
) -> str:
    if _text_width(text, font, scale, thickness) <= max_width:
        return text
    suffix = "..."
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = text[:mid].rstrip() + suffix
        if _text_width(candidate, font, scale, thickness) <= max_width:
            low = mid
        else:
            high = mid - 1
    if low <= 0:
        return suffix
    return text[:low].rstrip() + suffix


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
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return frame

    original = frame
    try:
        fingerprint = _fingerprint(frame)

        if frame.ndim == 2:
            canvas = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            canvas = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 3:
            canvas = frame.copy()
        else:
            return frame

        if canvas.dtype != np.uint8:
            canvas = np.clip(canvas, 0, 255).astype(np.uint8)

        height, width = canvas.shape[:2]
        if height < 16 or width < 16:
            return canvas

        md = metadata if isinstance(metadata, dict) else {}
        hotel = _clean_text(md.get("hotel_name"), "Unknown Hotel")
        location = _clean_text(md.get("location"), "Unassigned Location")
        raw_label = _clean_text(md.get("label"), "violation")
        class_name = _humanize_label(raw_label)
        category = _clean_text(md.get("category"), "").lower()
        if category not in ("pest", "hygiene"):
            category = "pest" if raw_label.strip().lower() in _PEST_LABELS else "hygiene"
        badge_text = "[PEST ALERT]" if category == "pest" else "[PPE BREACH]"
        badge_color = _PEST_BGR if category == "pest" else _HYGIENE_BGR
        ratio = _as_fraction(md.get("amfv_ratio"))
        confidence = _as_fraction(md.get("confidence"))
        timestamp = _clean_text(
            md.get("timestamp"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        line2 = f"{hotel} | {location} | {timestamp}"
        line3 = f"SHA256 Fingerprint: {fingerprint}"
        metric_texts = [
            f"AMFV Verified: {int(round(ratio * 100))}%",
            f"Conf: {int(round(confidence * 100))}%",
        ]

        ui = max(0.35, min(width / 1280.0, height / 720.0))
        ui = min(ui, 3.0)
        padding = max(5, int(round(14 * ui)))
        gap = max(3, int(round(8 * ui)))
        seg_gap = max(3, int(round(7 * ui)))
        badge_pad_x = max(3, int(round(7 * ui)))
        badge_pad_y = max(2, int(round(3 * ui)))
        bullet_radius = max(1, int(round(2 * ui)))
        title_scale = max(0.36, 0.60 * ui)
        body_scale = max(0.30, 0.44 * ui)
        mono_scale = max(0.30, 0.40 * ui)
        title_thickness = max(1, int(round(2 * ui)))
        body_thickness = max(1, int(round(ui)))
        mono_thickness = 1

        inner_width = max(20, width - 2 * padding)
        metric_scale = max(0.22, title_scale * 0.72)
        metric_thickness = max(1, title_thickness - 1)

        def line1_widths(scale: float) -> tuple[int, int, int]:
            badge_width = (
                _text_width(badge_text, _FONT_TITLE, scale, title_thickness)
                + 2 * badge_pad_x
            )
            class_width = _text_width(class_name, _FONT_TITLE, scale, title_thickness)
            total = badge_width + gap + class_width
            for metric in metric_texts:
                total += (
                    2 * seg_gap
                    + 2 * bullet_radius
                    + _text_width(metric, _FONT_BODY, metric_scale, metric_thickness)
                )
            return total, badge_width, class_width

        total_width, badge_width, class_width = line1_widths(title_scale)
        while total_width > inner_width and title_scale > 0.22:
            title_scale *= 0.94
            metric_scale = max(0.20, title_scale * 0.72)
            total_width, badge_width, class_width = line1_widths(title_scale)

        if total_width > inner_width:
            available = inner_width - (total_width - class_width) - seg_gap
            if available > 0:
                previous_class_width = class_width
                class_name = _truncate(
                    class_name,
                    _FONT_TITLE,
                    title_scale,
                    title_thickness,
                    available,
                )
                class_width = _text_width(
                    class_name, _FONT_TITLE, title_scale, title_thickness
                )
                total_width = total_width - previous_class_width + class_width

        body_scale = _fit_scale(
            line2, _FONT_BODY, body_scale, body_thickness, inner_width
        )
        line2 = _truncate(line2, _FONT_BODY, body_scale, body_thickness, inner_width)
        mono_scale = _fit_scale(
            line3, _FONT_MONO, mono_scale, mono_thickness, inner_width
        )
        line3 = _truncate(line3, _FONT_MONO, mono_scale, mono_thickness, inner_width)

        title_height = _text_height(
            badge_text, _FONT_TITLE, title_scale, title_thickness
        )
        metric_height = _text_height(
            metric_texts[0], _FONT_BODY, metric_scale, metric_thickness
        )
        line1_block_height = max(title_height, metric_height) + 2 * badge_pad_y
        line2_height = _text_height(line2, _FONT_BODY, body_scale, body_thickness)
        line3_height = _text_height(line3, _FONT_MONO, mono_scale, mono_thickness)

        content_height = (
            line1_block_height + gap + line2_height + gap + line3_height
        )
        banner_height = min(height, content_height + 2 * padding)
        banner_top = 0 if str(position).strip().lower() == "top" else height - banner_height

        overlay = canvas.copy()
        cv2.rectangle(
            overlay,
            (0, banner_top),
            (width - 1, banner_top + banner_height - 1),
            _BANNER_BGR,
            -1,
        )
        canvas = cv2.addWeighted(
            overlay, _BANNER_OPACITY, canvas, 1.0 - _BANNER_OPACITY, 0
        )

        line1_top = banner_top + padding
        baseline1 = line1_top + badge_pad_y + title_height
        line2_top = line1_top + line1_block_height + gap
        baseline2 = line2_top + line2_height
        line3_top = line2_top + line2_height + gap
        baseline3 = line3_top + line3_height

        x = padding
        cv2.rectangle(
            canvas,
            (x, line1_top),
            (x + badge_width - 1, line1_top + title_height + 2 * badge_pad_y - 1),
            badge_color,
            -1,
        )
        cv2.putText(
            canvas,
            badge_text,
            (x + badge_pad_x, baseline1),
            _FONT_TITLE,
            title_scale,
            _WHITE,
            title_thickness,
            cv2.LINE_AA,
        )
        x += badge_width + gap
        cv2.putText(
            canvas,
            class_name,
            (x, baseline1),
            _FONT_TITLE,
            title_scale,
            _WHITE,
            title_thickness,
            cv2.LINE_AA,
        )
        x += class_width

        for metric in metric_texts:
            x += seg_gap
            center_y = baseline1 - metric_height // 2
            cv2.circle(
                canvas,
                (x + bullet_radius, center_y),
                bullet_radius,
                _ZINC_400,
                -1,
                cv2.LINE_AA,
            )
            x += 2 * bullet_radius + seg_gap
            cv2.putText(
                canvas,
                metric,
                (x, baseline1),
                _FONT_BODY,
                metric_scale,
                _ZINC_400,
                metric_thickness,
                cv2.LINE_AA,
            )
            x += _text_width(metric, _FONT_BODY, metric_scale, metric_thickness)

        cv2.putText(
            canvas,
            line2,
            (padding, baseline2),
            _FONT_BODY,
            body_scale,
            _ZINC_400,
            body_thickness,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            line3,
            (padding, baseline3),
            _FONT_MONO,
            mono_scale,
            _ZINC_400,
            mono_thickness,
            cv2.LINE_AA,
        )

        return canvas
    except Exception as exc:
        print(f"[watermark] Failed to apply forensic watermark: {exc}")
        return original


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
    target = ""
    if output_path is not None:
        try:
            target = str(output_path).strip()
        except Exception:
            target = ""
    if not target:
        target = f"violation_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

    absolute_path = os.path.abspath(target)
    try:
        jpeg_quality = int(quality)
    except (TypeError, ValueError):
        jpeg_quality = 92
    jpeg_quality = max(1, min(100, jpeg_quality))

    try:
        parent = os.path.dirname(absolute_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        watermarked = apply_forensic_watermark(frame, metadata)
        if not isinstance(watermarked, np.ndarray) or watermarked.size == 0:
            print(f"[watermark] Unable to save snapshot: invalid frame for {absolute_path}")
            return absolute_path
        saved = cv2.imwrite(
            absolute_path,
            watermarked,
            [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
        )
        if not saved:
            print(f"[watermark] cv2.imwrite failed for {absolute_path}")
    except Exception as exc:
        print(f"[watermark] Failed to save watermarked snapshot '{absolute_path}': {exc}")
    return absolute_path


if __name__ == "__main__":
    demo_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    demo_metadata = {
        "hotel_name": "Grand Palace Hotel",
        "location": "Main Kitchen - Prep Counter",
        "camera_name": "Kitchen CCTV 1",
        "label": "no_apron",
        "category": "hygiene",
        "confidence": 0.88,
        "amfv_ratio": 0.50,
        "timestamp": "2026-11-13 18:30:00",
    }

    watermarked_frame = apply_forensic_watermark(demo_frame, demo_metadata)
    assert isinstance(watermarked_frame, np.ndarray)
    assert watermarked_frame.shape == demo_frame.shape

    top_watermarked = apply_forensic_watermark(
        demo_frame, demo_metadata, position="top"
    )
    assert top_watermarked.shape == demo_frame.shape

    apply_forensic_watermark(demo_frame, {})
    apply_forensic_watermark(demo_frame, None)

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_watermark.jpg"
    )
    saved_path = save_watermarked_snapshot(demo_frame, output_path, demo_metadata)
    if not os.path.exists(saved_path) or os.path.getsize(saved_path) <= 0:
        raise SystemExit(f"Watermark verification failed: {saved_path} was not created")

    print("Forensic watermark verification passed")
    print(f"Snapshot: {saved_path} ({os.path.getsize(saved_path)} bytes)")
    print(f"SHA256 fingerprint: {_fingerprint(demo_frame)}")
