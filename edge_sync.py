"""
Edge-to-Central Synchronization Client for Smart Hotel Monitoring System.
Runs in a background daemon thread on edge devices to communicate with SHMS Central Server.
"""

import os
import time
import json
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime


class EdgeSyncClient:
    """Handles edge registration, heartbeats, incident forwarding, and remote commands."""

    def __init__(self, db, camera_manager):
        self.db = db
        self.camera_manager = camera_manager
        self.central_url = os.getenv("CENTRAL_SERVER_URL", "http://127.0.0.1:9000").rstrip("/")
        self.edge_id = self._get_or_create_edge_id()
        self.name = self.db.get_setting("edge_name", "Kitchen Edge AI-01")
        self.hotel_name = self.db.get_setting("hotel_name", "Grand Hotel & Suites")
        self.location = self.db.get_setting("edge_location", "Main Prep Kitchen")
        self.running = False
        self._thread = None

    def _get_or_create_edge_id(self) -> str:
        edge_id = self.db.get_setting("edge_id", "")
        if not edge_id:
            import uuid
            edge_id = f"edge_{uuid.uuid4().hex[:8]}"
            self.db.set_setting("edge_id", edge_id)
        return edge_id

    def start(self):
        """Starts the periodic heartbeat and sync worker in a background thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        print(f"📡 [Edge Sync] Initialized edge worker [{self.edge_id}]. Central target: {self.central_url}")

    def _worker_loop(self):
        # 1. Initial Registration
        time.sleep(2)  # Give local cameras a moment to initialize
        self.register_with_central()

        # 2. Periodic Heartbeat Loop (every 10 seconds)
        while self.running:
            try:
                self.send_heartbeat()
            except Exception as e:
                # Silently catch so local edge processing is never interrupted
                pass
            time.sleep(10)

    def register_with_central(self):
        """Sends initial registration payload to Central Server."""
        try:
            cameras = self._get_cameras_telemetry()
            payload = {
                "edge_id": self.edge_id,
                "name": self.name,
                "hotel_name": self.hotel_name,
                "location": self.location,
                "api_url": os.getenv("EDGE_API_URL", "http://127.0.0.1:8000"),
                "cameras": cameras,
                "config": {
                    "window_size": self.camera_manager.cameras[list(self.camera_manager.cameras.keys())[0]].amfv_window_size if self.camera_manager.cameras else 2,
                    "threshold_pest": 0.20,
                    "threshold_hygiene": 0.40,
                }
            }

            req = urllib.request.Request(
                f"{self.central_url}/api/edge/register",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": f"SHMS-Edge/{self.edge_id}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(f"📡 [Edge Sync] Successfully registered with Central Fleet Server at {self.central_url}")
        except Exception:
            # Central server might not be running yet, will retry on heartbeat
            pass

    def send_heartbeat(self):
        """Sends telemetry and handles any remote commands returned by Central."""
        try:
            cameras = self._get_cameras_telemetry()
            telemetry = self._get_system_telemetry()

            payload = {
                "edge_id": self.edge_id,
                "telemetry": telemetry,
                "cameras": cameras,
            }

            req = urllib.request.Request(
                f"{self.central_url}/api/edge/heartbeat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": f"SHMS-Edge/{self.edge_id}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    commands = data.get("commands", [])
                    for cmd in commands:
                        self._handle_remote_command(cmd)
        except Exception:
            pass

    def forward_incident(
        self,
        camera_id: str,
        camera_name: str,
        label: str,
        timestamp: str,
        confidence: float,
        ratio: float,
        snapshot_path: str,
    ):
        """Uploads confirmed violation metadata and snapshot image to Central Server."""
        try:
            import base64
            category = "pest" if label in ["cockroach", "lizard", "rat"] else "hygiene"
            
            b64_snap = None
            if snapshot_path and os.path.exists(snapshot_path):
                try:
                    with open(snapshot_path, "rb") as f:
                        b64_snap = base64.b64encode(f.read()).decode("utf-8")
                except Exception as e:
                    print(f"⚠️ [Edge Sync] Snapshot read error: {e}")

            payload = {
                "edge_id": self.edge_id,
                "camera_id": camera_id,
                "camera_name": camera_name,
                "label": label,
                "category": category,
                "timestamp": timestamp,
                "confidence": confidence,
                "amfv_ratio": ratio,
                "snapshot_base64": b64_snap,
            }

            req = urllib.request.Request(
                f"{self.central_url}/api/edge/incident",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"SHMS-Edge/{self.edge_id}",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    print(f"📡 [Edge Sync] Uploaded confirmed {label.upper()} violation to Central Server")
        except Exception:
            # Central server might be temporarily unreachable, local edge continues normally
            pass

    def _get_cameras_telemetry(self) -> list:
        cams = []
        for c in self.camera_manager.list_cameras():
            cams.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "connected": c.get("connected"),
                "fps": c.get("fps"),
                "source_type": c.get("source_type"),
            })
        return cams

    def _get_system_telemetry(self) -> dict:
        telemetry = {}
        try:
            import psutil
            telemetry["cpu_percent"] = psutil.cpu_percent(interval=None)
            telemetry["memory_percent"] = psutil.virtual_memory().percent
        except ImportError:
            # Fallback if psutil is not installed
            telemetry["cpu_percent"] = None
            telemetry["memory_percent"] = None
        return telemetry

    def _handle_remote_command(self, cmd: dict):
        """Processes remote configuration update or command pushed from Central Admin."""
        cmd_type = cmd.get("type")
        payload = cmd.get("payload", {})

        print(f"📡 [Edge Sync] Received remote command from Central: {cmd_type} -> {payload}")

        if cmd_type == "update_config":
            w = payload.get("window_size")
            tp = payload.get("threshold_pest")
            th = payload.get("threshold_hygiene")
            cd = payload.get("cooldown")

            for stream in self.camera_manager.cameras.values():
                stream.update_amfv_config(
                    window_size=w,
                    threshold_pest=tp,
                    threshold_hygiene=th,
                    cooldown=cd,
                )

            if w is not None: self.db.update_setting("amfv_window_size", str(w))
            if tp is not None: self.db.update_setting("amfv_threshold_pest", str(tp))
            if th is not None: self.db.update_setting("amfv_threshold_hygiene", str(th))
            if cd is not None: self.db.update_setting("alert_cooldown", str(cd))

            print(f"✅ [Edge Sync] Remote AMFV parameters updated from Central Admin")

