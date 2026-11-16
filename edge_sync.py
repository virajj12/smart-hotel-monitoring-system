"""
Duplex edge-to-central synchronization manager for Smart Hotel Monitoring.

The manager keeps a persistent WebSocket open to the SHMS central server so the
fleet admin can request live snapshots and trigger syncs immediately. Confirmed
violations are batched over HTTP on an hourly interval (or on demand), and the
local ledger is only marked as synced after the central server acknowledges it.
"""

import base64
import hashlib
import json
import os
import platform
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import cv2
import websocket

try:
    import requests
except ImportError:
    requests = None


class EdgeSyncManager:
    """Owns the duplex connection, heartbeat, batch sync, and remote commands."""

    HEARTBEAT_INTERVAL = 10
    BATCH_LIMIT = 5
    MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
    MAX_BATCH_SNAPSHOT_BYTES = 2 * 1024 * 1024
    DEFAULT_OWNER_ID = "OWN-DEFAULT-SYSTEM"
    AUTO_SYNC_THRESHOLD = 5
    IDENTITY_FILE = ".edge_identity.json"

    @classmethod
    def get_hardware_fingerprint(cls) -> str:
        """Deterministic hardware fingerprint unique to this physical machine."""
        parts = [
            str(uuid.getnode()),
            platform.node(),
            platform.machine(),
            platform.system(),
        ]
        try:
            if platform.system() == "Windows":
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                    guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    parts.append(str(guid))
        except Exception:
            pass
        return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24].upper()

    def __init__(self, db, camera_manager):
        self.db = db
        self.camera_manager = camera_manager
        self.central_url = (
            self.db.get_setting("central_url", os.getenv("CENTRAL_SERVER_URL", "http://127.0.0.1:9000"))
            or ""
        ).rstrip("/")
        self.kitchen_id = self.db.get_setting("kitchen_id", "") or ""
        self.auth_token = self.db.get_setting("auth_token", "") or ""
        self.owner_id = self.db.get_setting("owner_id", self.DEFAULT_OWNER_ID) or self.DEFAULT_OWNER_ID
        self.hotel_name = self.db.get_setting("hotel_name", "Grand Hotel & Suites") or ""
        self.kitchen_name = self.db.get_setting(
            "kitchen_name", self.db.get_setting("edge_name", "Kitchen Edge AI-01")
        ) or ""
        self.location = self.db.get_setting("edge_location", "Main Prep Kitchen") or ""
        self.sync_interval_minutes = self._read_interval()
        try:
            self.auto_sync_threshold = int(self.db.get_setting("auto_sync_threshold", str(self.AUTO_SYNC_THRESHOLD)) or self.AUTO_SYNC_THRESHOLD)
        except Exception:
            self.auto_sync_threshold = self.AUTO_SYNC_THRESHOLD
        self.pending_request_id = self.db.get_setting("pending_request_id", "") or ""
        self.pending_pin = self.db.get_setting("pending_pin", "") or ""

        # Load & sync persistent identity from .edge_identity.json (git-ignored)
        self._load_persistent_identity()

        self.running = False
        self._thread = None
        self._enrollment_thread = None
        self._pending_lock = threading.Lock()
        self._ws = None
        self._ws_lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reconnect_event = threading.Event()
        self._epoch = 0
        self._ws_connected = False
        self._last_heartbeat = 0.0
        self._next_sync_at = 0.0
        self._backoff = 2
        self._last_error = ""
        self._last_sync_result = None

    def _load_persistent_identity(self):
        """Loads and synchronizes the persistent device identity from .edge_identity.json and SQLite."""
        identity = {}
        if os.path.exists(self.IDENTITY_FILE):
            try:
                with open(self.IDENTITY_FILE, "r", encoding="utf-8") as f:
                    identity = json.load(f)
            except Exception as e:
                print(f"[Edge Sync] Warning reading {self.IDENTITY_FILE}: {e}")

        # Deterministic machine hardware fingerprint
        hw_fp = identity.get("hardware_fingerprint") or self.get_hardware_fingerprint()
        dev_uuid = identity.get("device_uuid") or str(uuid.uuid4())
        self.hardware_fingerprint = hw_fp
        self.device_uuid = dev_uuid

        # Prioritize identity file if SQLite was wiped or empty, otherwise sync
        persisted_kitchen_id = identity.get("kitchen_id") or self.kitchen_id
        persisted_auth_token = identity.get("auth_token") or self.auth_token
        persisted_central_url = identity.get("central_url") or self.central_url

        self.kitchen_id = persisted_kitchen_id
        self.auth_token = persisted_auth_token
        if persisted_central_url:
            self.central_url = persisted_central_url

        # Sync back to SQLite settings so both stay in lockstep
        if self.kitchen_id:
            self.db.set_setting("kitchen_id", self.kitchen_id)
        if self.auth_token:
            self.db.set_setting("auth_token", self.auth_token)
        if self.central_url:
            self.db.set_setting("central_url", self.central_url)
        self.db.set_setting("hardware_fingerprint", self.hardware_fingerprint)

        # Write out any newly resolved identity fields
        self._save_persistent_identity()

    def _save_persistent_identity(self):
        """Atomically saves the persistent device identity to .edge_identity.json (git-ignored)."""
        data = {
            "device_uuid": getattr(self, "device_uuid", ""),
            "hardware_fingerprint": getattr(self, "hardware_fingerprint", ""),
            "kitchen_id": self.kitchen_id,
            "auth_token": self.auth_token,
            "central_url": self.central_url,
            "owner_id": self.owner_id,
            "hotel_name": self.hotel_name,
            "kitchen_name": self.kitchen_name,
            "location": self.location,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(self.IDENTITY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Edge Sync] Failed to save {self.IDENTITY_FILE}: {e}")

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self):
        """Start the background supervisor once."""
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="edge-sync", daemon=True)
        self._thread.start()
        print(f"[Edge Sync] Supervisor started (target: {self.central_url or 'not configured'})")

    def stop(self):
        """Stop the supervisor and close the WebSocket."""
        self.running = False
        self._stop_event.set()
        self._reconnect_event.set()
        self._close_ws()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    # ── Public API used by main.py ──────────────────────────────────────

    def connect_to_central(
        self,
        central_url: str,
        hotel_name: str,
        kitchen_name: str,
        location: str = "",
        owner_id: str = "OWN-DEFAULT-SYSTEM",
        pairing_code: str = "",
    ) -> dict:
        """Register this edge with the central multi-tenant server and open the duplex channel."""
        central_url = self._normalize_url(central_url)
        hotel_name = (hotel_name or "").strip()
        kitchen_name = (kitchen_name or "").strip()
        if not hotel_name or not kitchen_name:
            raise ValueError("Hotel name and kitchen name are required")

        payload = {
            "owner_id": (owner_id or self.owner_id or self.DEFAULT_OWNER_ID).strip(),
            "hotel_name": hotel_name,
            "kitchen_name": kitchen_name,
            "location": (location or "").strip(),
            "cameras_count": len(self.camera_manager.list_cameras()),
            "cameras": self._get_cameras_telemetry(),
            "system_info": {
                "hostname": platform.node(),
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
        }
        if self.kitchen_id:
            payload["kitchen_id"] = self.kitchen_id
        if self.auth_token:
            payload["auth_token"] = self.auth_token

        # Stable machine identity
        payload["hardware_fingerprint"] = getattr(self, "hardware_fingerprint", self.get_hardware_fingerprint())
        payload["device_uuid"] = getattr(self, "device_uuid", "")

        if pairing_code:
            code_clean = pairing_code.strip().upper()
            payload["pairing_pin"] = code_clean
            payload["pairing_code"] = code_clean

        api_url = os.getenv("EDGE_API_URL")
        if api_url:
            payload["api_url"] = api_url

        response = self._post_json(
            f"{central_url}/api/edge/request_connection", payload, timeout=10
        )
        status_value = str(response.get("status") or "approved").lower()
        request_id = str(response.get("request_id") or "")
        assigned_id = str(response.get("kitchen_id") or "")

        # Always capture and store the central-assigned device ID immediately
        if assigned_id:
            self.kitchen_id = assigned_id
            self.db.set_setting("kitchen_id", self.kitchen_id)
            self._save_persistent_identity()

        if status_value == "pending":
            self.central_url = central_url
            self.owner_id = (owner_id or self.owner_id or self.DEFAULT_OWNER_ID).strip()
            self.hotel_name = hotel_name
            self.kitchen_name = kitchen_name
            self.location = (location or "").strip()
            self.pending_request_id = request_id
            self.pending_pin = str(response.get("pin") or "")
            if not self.kitchen_id:
                self.kitchen_id = assigned_id
            self.auth_token = ""
            self.db.set_setting("central_url", self.central_url)
            self.db.set_setting("kitchen_id", self.kitchen_id)
            self.db.set_setting("auth_token", "")
            self.db.set_setting("owner_id", self.owner_id)
            self.db.set_setting("hotel_name", self.hotel_name)
            self.db.set_setting("kitchen_name", self.kitchen_name)
            self.db.set_setting("edge_name", self.kitchen_name)
            self.db.set_setting("edge_location", self.location)
            self.db.set_setting("pending_request_id", self.pending_request_id)
            self.db.set_setting("pending_pin", self.pending_pin)
            self._save_persistent_identity()
            self._start_enrollment_poll(
                central_url, request_id, hotel_name, kitchen_name, location, owner_id
            )
            result = dict(response)
            result["success"] = False
            result["status"] = "pending"
            return result

        if status_value != "approved":
            raise RuntimeError(f"Enrollment status: {status_value}")

        if not response.get("auth_token"):
            credentials = self._get_json(
                f"{central_url}/api/edge/enrollment/{request_id}/credentials",
                timeout=5,
            )
            response = {**response, **credentials}

        return self._apply_enrollment(
            response, central_url, hotel_name, kitchen_name, location, owner_id
        )

    def _start_enrollment_poll(
        self,
        central_url: str,
        request_id: str,
        hotel_name: str,
        kitchen_name: str,
        location: str,
        owner_id: str,
    ) -> None:
        """Start a background thread that waits for owner approval."""
        with self._pending_lock:
            if self._enrollment_thread and self._enrollment_thread.is_alive():
                return
            self._enrollment_thread = threading.Thread(
                target=self._await_enrollment_approval,
                args=(central_url, request_id, hotel_name, kitchen_name, location, owner_id),
                name="edge-enrollment",
                daemon=True,
            )
            self._enrollment_thread.start()

    def _await_enrollment_approval(
        self,
        central_url: str,
        request_id: str,
        hotel_name: str,
        kitchen_name: str,
        location: str,
        owner_id: str,
    ) -> None:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            try:
                status_response = self._get_json(
                    f"{central_url}/api/edge/connection_status/{request_id}", timeout=5
                )
                status_value = str(status_response.get("status") or "pending").lower()
                if status_value in ("rejected", "revoked"):
                    with self._status_lock:
                        self._last_error = (
                            status_response.get("rejection_reason")
                            or f"Enrollment {status_value}"
                        )
                    self._clear_pending_enrollment()
                    return
                if status_value == "approved":
                    if not status_response.get("auth_token"):
                        credentials = self._get_json(
                            f"{central_url}/api/edge/enrollment/{request_id}/credentials",
                            timeout=5,
                        )
                        status_response = {**status_response, **credentials}
                    self._apply_enrollment(
                        status_response, central_url, hotel_name, kitchen_name, location, owner_id
                    )
                    return
            except Exception as exc:  # Keep polling through transient central outages.
                with self._status_lock:
                    self._last_error = f"Waiting for approval: {exc}"
            time.sleep(3)
        with self._status_lock:
            self._last_error = "Timed out waiting for owner approval"
        self._clear_pending_enrollment()

    def _clear_pending_enrollment(self) -> None:
        self.pending_request_id = ""
        self.pending_pin = ""
        self.db.set_setting("pending_request_id", "")
        self.db.set_setting("pending_pin", "")

    def _apply_enrollment(
        self,
        response: dict,
        central_url: str,
        hotel_name: str,
        kitchen_name: str,
        location: str,
        owner_id: str,
    ) -> dict:
        kitchen_id = response.get("kitchen_id")
        auth_token = response.get("auth_token")
        if not kitchen_id or not auth_token:
            raise RuntimeError("Central server did not return a kitchen ID and auth token")

        self.central_url = central_url
        self.kitchen_id = kitchen_id
        self.auth_token = auth_token
        self.owner_id = str(response.get("owner_id") or owner_id or self.owner_id or self.DEFAULT_OWNER_ID)
        self.hotel_name = hotel_name
        self.kitchen_name = kitchen_name
        self.location = (location or "").strip()
        self.sync_interval_minutes = int(response.get("sync_interval_minutes") or 60)
        self._clear_pending_enrollment()

        self.db.set_setting("central_url", self.central_url)
        self.db.set_setting("kitchen_id", self.kitchen_id)
        self.db.set_setting("auth_token", self.auth_token)
        self.db.set_setting("owner_id", self.owner_id)
        self.db.set_setting("duplex_endpoint", response.get("duplex_endpoint") or f"/ws/edge/{self.kitchen_id}")
        self.db.set_setting("sync_interval_minutes", str(self.sync_interval_minutes))
        self.db.set_setting("hotel_name", self.hotel_name)
        self.db.set_setting("kitchen_name", self.kitchen_name)
        self.db.set_setting("edge_name", self.kitchen_name)
        self.db.set_setting("edge_location", self.location)
        if response.get("supabase_url"):
            self.db.set_setting("supabase_url", response.get("supabase_url"))
        if response.get("supabase_anon_key"):
            self.db.set_setting("supabase_anon_key", response.get("supabase_anon_key"))
        if response.get("supabase_bucket"):
            self.db.set_setting("supabase_bucket", response.get("supabase_bucket"))

        # Save identity & credentials to .edge_identity.json permanently
        self._save_persistent_identity()

        with self._status_lock:
            self._last_error = ""
        was_running = self.running
        self._epoch += 1
        self.start()
        if was_running:
            self._reconnect_event.set()
        self._close_ws()

        result = self.get_status()
        result["success"] = True
        result["duplex_endpoint"] = response.get("duplex_endpoint") or f"/ws/edge/{self.kitchen_id}"
        return result

    def get_status(self) -> dict:
        """Return connection and local sync-ledger status for the dashboard."""
        try:
            ledger = self.db.get_sync_status()
        except Exception as exc:
            ledger = {
                "total_count": 0,
                "synced_count": 0,
                "unsynced_count": 0,
                "last_synced_at": None,
                "ledger_error": str(exc),
            }
        with self._status_lock:
            last_error = self._last_error
            last_sync_result = self._last_sync_result
        return {
            "configured": bool(self.central_url and self.kitchen_id and self.auth_token),
            "connected": self._ws_connected,
            "central_url": self.central_url,
            "kitchen_id": self.kitchen_id,
            "hardware_fingerprint": getattr(self, "hardware_fingerprint", ""),
            "device_uuid": getattr(self, "device_uuid", ""),
            "owner_id": self.owner_id,
            "pending_request_id": self.pending_request_id,
            "pending_pin": self.pending_pin,
            "enrollment_status": (
                "pending" if self.pending_request_id else ("approved" if self.auth_token else "unconfigured")
            ),
            "hotel_name": self.hotel_name,
            "kitchen_name": self.kitchen_name,
            "location": self.location,
            "sync_interval_minutes": self.sync_interval_minutes,
            "last_error": last_error,
            "last_sync_result": last_sync_result,
            **ledger,
        }

    def sync_now(self) -> dict:
        """Run one batch sync synchronously and return its result."""
        return self._run_batch_sync(reason="manual")

    def trigger_sync(self, reason: str = "remote") -> dict:
        """Schedule one batch sync in the background (used by the WS command or internal trigger)."""
        if not self._has_credentials():
            return {"success": False, "error": "Central connection is not configured"}
        threading.Thread(
            target=self._run_batch_sync,
            kwargs={"reason": reason},
            name=f"edge-sync-{reason}",
            daemon=True,
        ).start()
        return {"success": True, "message": "Sync scheduled"}

    def notify_new_violation(self):
        """Immediately checks if unsynced violations/snapshots exceed threshold (>= 5) and triggers sync."""
        if not self._has_credentials():
            return
        try:
            status = self.db.get_sync_status()
            unsynced = status.get("unsynced_count", 0)
            if unsynced >= self.auto_sync_threshold:
                print(f"[Edge Sync] Auto-sync triggered: {unsynced} unsynced snapshots (threshold >= {self.auto_sync_threshold})")
                self.trigger_sync(reason="threshold_exceeded")
        except Exception as exc:
            pass

    # ── Supervisor loop ─────────────────────────────────────────────────

    def _worker_loop(self):
        print(f"[Edge Sync] Supervisor running (HTTP Poller -> {self.central_url or 'unconfigured'})")
        while self.running:
            if not self._has_credentials():
                self._set_ws_connected(False)
                self._reconnect_event.wait(2)
                self._reconnect_event.clear()
                continue

            epoch = self._epoch
            try:
                # 1. Local unsynced ledger count
                try:
                    ledger = self.db.get_sync_status()
                except Exception:
                    ledger = {"unsynced_count": 0}

                # 2. Build heartbeat payload
                payload = {
                    "edge_id": self.kitchen_id,
                    "auth_token": self.auth_token,
                    "telemetry": self._get_system_telemetry(),
                    "cameras": self._get_cameras_telemetry(),
                    "unsynced_incidents": ledger.get("unsynced_count", 0),
                }

                # 3. HTTP poll to central server
                resp = self._post_json(
                    f"{self.central_url}/api/edge/poll",
                    payload,
                    timeout=6,
                )

                if resp.get("success"):
                    self._set_ws_connected(True)
                    with self._status_lock:
                        self._last_error = ""
                    self._backoff = 2
                    self._last_heartbeat = time.monotonic()

                    # Process commands from central server queue
                    commands = resp.get("commands") or []
                    for cmd in commands:
                        self._handle_command(cmd)

                    # Trigger auto-sync if unsynced snapshots reach threshold (>= 5), or periodic sync
                    now = time.monotonic()
                    unsynced = ledger.get("unsynced_count", 0)
                    if unsynced >= self.auto_sync_threshold:
                        self._schedule_background_sync("threshold_exceeded")
                    elif now >= self._next_sync_at:
                        self._next_sync_at = now + self.sync_interval_minutes * 60
                        self._schedule_background_sync("hourly")
                    elif unsynced > 0 and (now - self._last_heartbeat >= 60):
                        self._schedule_background_sync("unsynced_drain")
                else:
                    self._set_ws_connected(False)
                    with self._status_lock:
                        self._last_error = resp.get("detail") or "Poll rejected by central server"
            except Exception as exc:
                self._set_ws_connected(False)
                with self._status_lock:
                    self._last_error = f"Central link offline: {exc}"

            if not self.running:
                break
            if epoch != self._epoch:
                self._reconnect_event.clear()
                continue

            wait_seconds = 3 if self._ws_connected else min(15, self._backoff * 2)
            if not self._ws_connected:
                self._backoff = min(30, self._backoff * 2)
            self._reconnect_event.wait(wait_seconds)
            self._reconnect_event.clear()

    # ── Batch synchronization ───────────────────────────────────────────

    def _run_batch_sync(self, reason: str = "manual") -> dict:
        if not self._has_credentials():
            result = {"success": False, "error": "Central connection is not configured"}
            self._store_sync_result(result)
            return result
        if not self._sync_lock.acquire(blocking=False):
            return {"success": False, "error": "A sync is already in progress"}
        try:
            rows = self.db.get_unsynced_violations(limit=self.BATCH_LIMIT)
            if not rows:
                result = {
                    "success": True,
                    "synced_count": 0,
                    "requested_count": 0,
                    "unsynced_count": 0,
                    "message": "No unsynced violations",
                }
                self._store_sync_result(result)
                return result

            incidents = []
            encoded_snapshot_bytes = 0
            for row in rows:
                incident, _ = self._build_incident(row, allow_direct_upload=False)
                encoded_size = len(incident.get("snapshot_base64") or "")
                if (
                    incidents
                    and encoded_snapshot_bytes + encoded_size
                    > self.MAX_BATCH_SNAPSHOT_BYTES
                ):
                    break
                incidents.append(incident)
                encoded_snapshot_bytes += encoded_size

            ledger_before = self.db.get_sync_status()
            payload = {
                "kitchen_id": self.kitchen_id,
                "edge_id": self.kitchen_id,
                "auth_token": self.auth_token,
                "incidents": incidents,
                "remaining_unsynced": max(
                    0, ledger_before["unsynced_count"] - len(incidents)
                ),
            }
            response = self._post_json(
                f"{self.central_url}/api/edge/batch_sync", payload, timeout=45
            )
            synced_ids = (
                response.get("synced_ids")
                or response.get("synced_local_ids")
                or []
            )
            marked = self.db.mark_violations_synced(synced_ids) if synced_ids else 0
            ledger = self.db.get_sync_status()
            result = {
                "success": True,
                "reason": reason,
                "requested_count": len(incidents),
                "synced_count": marked,
                "unsynced_count": ledger["unsynced_count"],
                "message": f"Central accepted {marked} of {len(incidents)} incidents ({ledger['unsynced_count']} remaining)",
            }
            with self._status_lock:
                self._last_error = ""
            self._store_sync_result(result)
            print(f"[Edge Sync] {result['message']}")

            # If more unsynced items exist, auto-trigger next batch in background to drain queue
            if marked > 0 and ledger["unsynced_count"] > 0:
                self._schedule_background_sync("drain")

            return result
        except Exception as exc:
            try:
                unsynced = self.db.get_sync_status()["unsynced_count"]
            except Exception:
                unsynced = None
            result = {
                "success": False,
                "reason": reason,
                "error": str(exc),
                "unsynced_count": unsynced,
            }
            with self._status_lock:
                self._last_error = str(exc)
            self._store_sync_result(result)
            print(f"[Edge Sync] Batch sync failed: {exc}")
            return result
        finally:
            self._sync_lock.release()

    def _schedule_background_sync(self, reason: str):
        threading.Thread(
            target=self._run_batch_sync,
            kwargs={"reason": reason},
            name=f"edge-sync-{reason}",
            daemon=True,
        ).start()

    def _upload_snapshot_to_supabase(self, local_path: str, filename: str) -> str | None:
        """Uploads a violation JPEG directly to Supabase Storage and returns the public CDN URL."""
        supabase_url = (
            self.db.get_setting("supabase_url", "")
            or os.getenv("SUPABASE_URL", "")
            or ""
        ).rstrip("/")
        supabase_key = (
            self.db.get_setting("supabase_anon_key", "")
            or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
            or os.getenv("SUPABASE_ANON_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
            or ""
        )
        supabase_bucket = (
            self.db.get_setting("supabase_bucket", "")
            or os.getenv("SUPABASE_BUCKET", "")
            or "evidence-snapshots"
        )
        if not supabase_url or not supabase_key:
            return None
        try:
            with open(local_path, "rb") as handle:
                raw_bytes = handle.read()
            upload_url = f"{supabase_url}/storage/v1/object/{supabase_bucket}/incidents/{filename}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": "image/jpeg",
                "x-upsert": "true",
            }
            if requests is not None:
                resp = requests.post(upload_url, data=raw_bytes, headers=headers, timeout=3)
                if resp.status_code in (200, 201):
                    return f"{supabase_url}/storage/v1/object/public/{supabase_bucket}/incidents/{filename}"
                resp = requests.put(upload_url, data=raw_bytes, headers=headers, timeout=3)
                if resp.status_code in (200, 201):
                    return f"{supabase_url}/storage/v1/object/public/{supabase_bucket}/incidents/{filename}"
            else:
                # Standard-library fallback
                req = urllib.request.Request(upload_url, data=raw_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status in (200, 201):
                        return f"{supabase_url}/storage/v1/object/public/{supabase_bucket}/incidents/{filename}"
        except Exception:
            pass
        return None

    def _build_incident(self, row: dict, allow_direct_upload: bool = True) -> tuple[dict, bool]:
        camera_id = row.get("camera_id") or ""
        cam = self.camera_manager.get_camera(camera_id) if camera_id else None
        snapshot_path = row.get("snapshot_path")
        snapshot_url = None
        snapshot_b64 = None
        direct_ok = allow_direct_upload
        filename = None

        if snapshot_path and os.path.exists(snapshot_path):
            filename = os.path.basename(snapshot_path)
            # 1. Attempt direct upload to Supabase Storage if allowed
            if allow_direct_upload:
                snapshot_url = self._upload_snapshot_to_supabase(snapshot_path, filename)
                if not snapshot_url:
                    direct_ok = False
            # 2. Fallback to base64 so Central Server can upload or store
            if not snapshot_url:
                snapshot_b64 = self._read_snapshot(snapshot_path)

        incident = {
            "local_id": row["id"],
            "local_violation_id": row["id"],
            "camera_id": camera_id,
            "camera_name": cam.name if cam else (camera_id or "Unknown"),
            "label": row["label"],
            "category": row.get("category") or "hygiene",
            "timestamp": row["timestamp"],
            "confidence": row.get("confidence", 0.0),
            "amfv_ratio": row.get("amfv_ratio", 0.0),
            "snapshot_filename": filename,
            "snapshot_url": snapshot_url,
            "snapshot_base64": snapshot_b64,
            "snapshot_b64": snapshot_b64,
        }
        return incident, direct_ok

    @classmethod
    def _read_snapshot(cls, snapshot_path: str | None) -> str | None:
        if not snapshot_path:
            return None
        try:
            with open(snapshot_path, "rb") as handle:
                raw = handle.read()
            if len(raw) > cls.MAX_SNAPSHOT_BYTES:
                print(
                    f"[Edge Sync] Skipping oversized snapshot "
                    f"({len(raw)} bytes): {snapshot_path}"
                )
                return None
            return base64.b64encode(raw).decode("utf-8")
        except (OSError, ValueError):
            return None

    def _store_sync_result(self, result: dict):
        with self._status_lock:
            self._last_sync_result = {
                **result,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
            }

    # ── WebSocket message handling ──────────────────────────────────────

    def _handle_message(self, raw: str):
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            return
        action = message.get("action") or message.get("type")
        if action == "capture_snapshot":
            self._send_snapshot(message.get("camera_id"), message.get("request_id"))
        elif action in ("trigger_sync", "sync_now"):
            self.trigger_sync()
        elif action == "update_config":
            self._apply_config(message.get("config") or message.get("payload") or {})
        elif action == "heartbeat_ack":
            return

    def _send_snapshot(self, camera_id: str | None, request_id: str | None):
        camera = None
        resolved_id = camera_id or ""
        if resolved_id and resolved_id not in ("all", "*"):
            camera = self.camera_manager.get_camera(resolved_id)
        if camera is None:
            cameras = self.camera_manager.list_cameras()
            if cameras:
                resolved_id = cameras[0]["id"]
                camera = self.camera_manager.get_camera(resolved_id)

        if camera is None:
            self._send_json(
                {
                    "event": "snapshot_reply",
                    "request_id": request_id,
                    "error": "No camera is available on this edge node",
                }
            )
            return

        frame = camera.get_raw_frame()
        if frame is None:
            self._send_json(
                {
                    "event": "snapshot_reply",
                    "request_id": request_id,
                    "camera_id": resolved_id,
                    "error": "Camera has no frame yet",
                }
            )
            return

        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        )
        if not ok:
            self._send_json(
                {
                    "event": "snapshot_reply",
                    "request_id": request_id,
                    "camera_id": resolved_id,
                    "error": "Failed to encode snapshot",
                }
            )
            return

        self._send_json(
            {
                "event": "snapshot_reply",
                "request_id": request_id,
                "camera_id": resolved_id,
                "camera_name": camera.name,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "image_base64": base64.b64encode(buffer.tobytes()).decode("utf-8"),
            }
        )

    def _apply_config(self, config: dict):
        if not isinstance(config, dict):
            return
        window_size = config.get("window_size")
        threshold_pest = config.get("threshold_pest")
        threshold_hygiene = config.get("threshold_hygiene")
        cooldown = config.get("cooldown")

        # Validate types and bounds before applying and persisting
        try:
            ws = int(window_size) if window_size is not None and int(window_size) > 0 else None
        except (ValueError, TypeError):
            ws = None

        try:
            tp = float(threshold_pest) if threshold_pest is not None and 0.0 < float(threshold_pest) <= 1.0 else None
        except (ValueError, TypeError):
            tp = None

        try:
            th = float(threshold_hygiene) if threshold_hygiene is not None and 0.0 < float(threshold_hygiene) <= 1.0 else None
        except (ValueError, TypeError):
            th = None

        try:
            cd = int(cooldown) if cooldown is not None and int(cooldown) >= 0 else None
        except (ValueError, TypeError):
            cd = None

        for stream in self.camera_manager.cameras.values():
            stream.update_amfv_config(
                window_size=ws,
                threshold_pest=tp,
                threshold_hygiene=th,
                cooldown=cd,
            )

        if ws is not None:
            self.db.set_setting("amfv_window", str(ws))
        if tp is not None:
            self.db.set_setting("amfv_threshold_pest", str(tp))
        if th is not None:
            self.db.set_setting("amfv_threshold_hygiene", str(th))
        if cd is not None:
            self.db.set_setting("cooldown_seconds", str(cd))

    def _send_heartbeat(self):
        try:
            ledger = self.db.get_sync_status()
        except Exception:
            ledger = {"unsynced_count": 0}
        self._last_heartbeat = time.monotonic()
        payload = {
            "event": "heartbeat",
            "edge_id": self.kitchen_id,
            "status": "online",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "telemetry": self._get_system_telemetry(),
            "cameras": self._get_cameras_telemetry(),
            "unsynced_incidents": ledger.get("unsynced_count", 0),
        }
        sent_ws = self._send_json(payload)
        if not sent_ws and self._has_credentials():
            # Fallback for Vercel/serverless hosts where persistent WebSockets are not maintained:
            # Deliver heartbeat over HTTP and process queued commands.
            try:
                resp = self._post_json(
                    f"{self.central_url}/api/edge/heartbeat",
                    payload,
                    timeout=6,
                )
                commands = resp.get("commands") or []
                for cmd in commands:
                    self._handle_command(cmd)
            except Exception:
                pass

    def _handle_command(self, cmd: dict):
        if not isinstance(cmd, dict):
            return
        cmd_id = cmd.get("id")
        cmd_type = cmd.get("command") or cmd.get("type") or cmd.get("action")
        payload = cmd.get("payload") or cmd.get("config") or {}
        camera_id = cmd.get("camera_id") or payload.get("camera_id")

        if cmd_type == "capture_snapshot":
            self._execute_snapshot_command(cmd_id, camera_id)
        elif cmd_type in ("trigger_sync", "sync_now"):
            self.trigger_sync()
        elif cmd_type == "update_config":
            self._apply_config(payload)

    def _execute_snapshot_command(self, command_id: str | None, camera_id: str | None):
        """Captures on-demand live snapshot and sends it directly to Central Server as ephemeral base64."""
        camera = None
        resolved_id = camera_id or ""
        if resolved_id and resolved_id not in ("all", "*"):
            camera = self.camera_manager.get_camera(resolved_id)
        if camera is None:
            cameras = self.camera_manager.list_cameras()
            if cameras:
                resolved_id = cameras[0]["id"]
                camera = self.camera_manager.get_camera(resolved_id)

        if camera is None:
            if command_id:
                self._send_command_reply(command_id, status="failed", error_message="No camera available")
            return

        frame = camera.get_raw_frame()
        if frame is None:
            if command_id:
                self._send_command_reply(command_id, status="failed", error_message="Camera has no frame yet")
            return

        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            if command_id:
                self._send_command_reply(command_id, status="failed", error_message="Failed to encode JPEG")
            return

        b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
        if command_id:
            self._send_command_reply(command_id, status="completed", image_base64=b64, camera_id=resolved_id)

    def _send_command_reply(
        self,
        command_id: str,
        status: str = "completed",
        image_base64: str | None = None,
        error_message: str | None = None,
        camera_id: str | None = None,
    ):
        payload = {
            "command_id": command_id,
            "edge_id": self.kitchen_id,
            "status": status,
        }
        if image_base64:
            payload["image_base64"] = image_base64
        if error_message:
            payload["error_message"] = error_message
        if camera_id:
            payload["camera_id"] = camera_id
        try:
            self._post_json(f"{self.central_url}/api/edge/command_reply", payload, timeout=8)
        except Exception as exc:
            print(f"[Edge Sync] Failed to send command reply: {exc}")

    def _send_json(self, payload: dict) -> bool:
        with self._ws_lock:
            ws = self._ws
        if ws is None:
            return False
        try:
            ws.send(json.dumps(payload))
            return True
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────────

    def _has_credentials(self) -> bool:
        return bool(self.central_url and self.kitchen_id and self.auth_token)

    def _read_interval(self) -> int:
        try:
            return max(1, int(self.db.get_setting("sync_interval_minutes", "60") or 60))
        except (TypeError, ValueError):
            return 60

    @staticmethod
    def _normalize_url(url: str) -> str:
        normalized = (url or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("Central server URL is required")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"http://{normalized}"
        parsed = urllib.parse.urlsplit(normalized)
        if not parsed.netloc:
            raise ValueError("Central server URL is invalid")
        return normalized

    def _build_ws_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.central_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        base_path = parsed.path.rstrip("/")
        duplex = (self.db.get_setting("duplex_endpoint", "") or "").strip()

        if duplex:
            duplex_parsed = urllib.parse.urlsplit(duplex)
            if duplex_parsed.scheme in ("ws", "wss"):
                ws_url = duplex
            elif duplex_parsed.scheme in ("http", "https"):
                ws_url = urllib.parse.urlunsplit(
                    (scheme, duplex_parsed.netloc, duplex_parsed.path, "", "")
                )
            else:
                ws_url = f"{scheme}://{parsed.netloc}{base_path}/{duplex.lstrip('/')}"
        else:
            ws_url = f"{scheme}://{parsed.netloc}{base_path}/ws/edge/{self.kitchen_id}"

        separator = "&" if "?" in ws_url else "?"
        return f"{ws_url}{separator}token={urllib.parse.quote(self.auth_token, safe='')}"

    def _set_ws_connected(self, connected: bool):
        self._ws_connected = connected

    def _close_ws(self):
        with self._ws_lock:
            ws = self._ws
            self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        self._set_ws_connected(False)

    @staticmethod
    def _get_json(url: str, timeout: int = 10) -> dict:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SmartHotelMonitor/2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                error_body = exc.read().decode("utf-8")
                detail = json.loads(error_body).get("detail", error_body)
            except Exception:
                detail = str(exc.reason)
            raise RuntimeError(f"Central server returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach central server: {exc.reason}") from exc

    @staticmethod
    def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
        if requests is not None:
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"User-Agent": "SHMS-Edge/2.0"},
                    timeout=timeout,
                )
                if resp.status_code >= 400:
                    detail = ""
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    raise RuntimeError(f"Central server returned HTTP {resp.status_code}: {detail}")
                return resp.json() if resp.text else {}
            except requests.RequestException as exc:
                raise RuntimeError(f"Cannot reach central server: {exc}") from exc

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SHMS-Edge/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                error_body = exc.read().decode("utf-8")
                detail = json.loads(error_body).get("detail", error_body)
            except Exception:
                detail = str(exc.reason)
            raise RuntimeError(f"Central server returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach central server: {exc.reason}") from exc

    def _get_cameras_telemetry(self) -> list:
        cameras = []
        try:
            for camera in self.camera_manager.list_cameras():
                cameras.append(
                    {
                        "id": camera.get("id"),
                        "name": camera.get("name"),
                        "connected": camera.get("connected"),
                        "fps": camera.get("fps"),
                        "source_type": camera.get("source_type"),
                    }
                )
        except Exception:
            return []
        return cameras

    @staticmethod
    def _get_system_telemetry() -> dict:
        telemetry = {"cpu_percent": None, "memory_percent": None}
        try:
            import psutil

            telemetry["cpu_percent"] = psutil.cpu_percent(interval=None)
            telemetry["memory_percent"] = psutil.virtual_memory().percent
        except ImportError:
            pass
        return telemetry
