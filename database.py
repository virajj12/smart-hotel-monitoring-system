"""
SQLite persistence layer for cameras and violations.
Thread-safe via threading.local() connections.
"""

import sqlite3
import threading
from datetime import datetime


class Database:
    def __init__(self, db_path: str = "hotel_monitoring.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cameras (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT DEFAULT '',
                source_type TEXT DEFAULT 'rtsp' CHECK(source_type IN ('rtsp', 'http', 'webcam', 'file')),
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                username TEXT DEFAULT '',
                password TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT,
                label TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                amfv_verified INTEGER DEFAULT 0,
                amfv_ratio REAL DEFAULT 0.0,
                snapshot_path TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        conn.commit()

    # ── Camera CRUD ──────────────────────────────────────────────────────

    def add_camera(
        self,
        camera_id: str,
        name: str,
        source: str,
        location: str = "",
        source_type: str = "rtsp",
        enabled: int = 1,
        username: str = "",
        password: str = "",
    ) -> dict:
        """Add a new camera to the database."""
        conn = self._get_conn()
        created_at = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO cameras (id, name, source, location, source_type, enabled, created_at, username, password)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (camera_id, name, source, location, source_type, enabled, created_at, username, password),
        )
        conn.commit()
        return self.get_camera(camera_id)

    def get_camera(self, camera_id: str) -> dict | None:
        """Get a single camera by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_cameras(self) -> list[dict]:
        """List all cameras."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM cameras ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def update_camera(self, camera_id: str, **kwargs) -> dict | None:
        """Update camera fields. Only updates provided keyword arguments."""
        allowed = {"name", "source", "location", "source_type", "enabled", "username", "password"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return self.get_camera(camera_id)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [camera_id]
        conn = self._get_conn()
        conn.execute(f"UPDATE cameras SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return self.get_camera(camera_id)

    def delete_camera(self, camera_id: str) -> bool:
        """Delete a camera by ID."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ── Violation CRUD ───────────────────────────────────────────────────

    def add_violation(
        self,
        camera_id: str,
        label: str,
        timestamp: str,
        amfv_verified: int = 0,
        amfv_ratio: float = 0.0,
        snapshot_path: str = "",
        confidence: float = 0.0,
    ) -> int:
        """Add a violation record. Returns the new row ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO violations (camera_id, label, timestamp, amfv_verified, amfv_ratio, snapshot_path, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (camera_id, label, timestamp, amfv_verified, amfv_ratio, snapshot_path, confidence),
        )
        conn.commit()
        return cursor.lastrowid

    def get_violations(
        self,
        camera_id: str | None = None,
        label: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get violations with optional filtering."""
        conn = self._get_conn()
        query = "SELECT * FROM violations WHERE 1=1"
        params: list = []

        if camera_id is not None:
            query += " AND camera_id = ?"
            params.append(camera_id)
        if label is not None:
            query += " AND label = ?"
            params.append(label)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_violation_stats(self, camera_id: str | None = None) -> dict:
        """
        Return violation statistics.
        Returns {total, pest, hygiene, breakdown} where pests = cockroach/lizard/rat.
        """
        conn = self._get_conn()
        base_where = "WHERE 1=1"
        params: list = []
        if camera_id is not None:
            base_where += " AND camera_id = ?"
            params.append(camera_id)

        # Total count
        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM violations {base_where}", params
        ).fetchone()["cnt"]

        # Pest count
        pest_labels = ("cockroach", "lizard", "rat")
        pest_placeholders = ",".join("?" for _ in pest_labels)
        pest_params = params + list(pest_labels)
        pest = conn.execute(
            f"SELECT COUNT(*) as cnt FROM violations {base_where} AND label IN ({pest_placeholders})",
            pest_params,
        ).fetchone()["cnt"]

        hygiene = total - pest

        # Breakdown by label
        breakdown_rows = conn.execute(
            f"SELECT label, COUNT(*) as cnt FROM violations {base_where} GROUP BY label ORDER BY cnt DESC",
            params,
        ).fetchall()
        breakdown = {row["label"]: row["cnt"] for row in breakdown_rows}

        return {
            "total": total,
            "pest": pest,
            "hygiene": hygiene,
            "breakdown": breakdown,
        }

    def clear_violations(self, camera_id: str | None = None) -> int:
        """Clear violations, optionally for a specific camera. Returns deleted count."""
        conn = self._get_conn()
        if camera_id is not None:
            cursor = conn.execute("DELETE FROM violations WHERE camera_id = ?", (camera_id,))
        else:
            cursor = conn.execute("DELETE FROM violations")
        conn.commit()
        return cursor.rowcount

    def acknowledge_violation(self, violation_id: int) -> bool:
        """Mark a violation as acknowledged."""
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE violations SET acknowledged = 1 WHERE id = ?", (violation_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    # ── Settings CRUD ────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Get a single setting value by key."""
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        """Insert or replace a setting value."""
        conn = self._get_conn()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

    def get_all_settings(self) -> dict[str, str]:
        """Return all settings as a key-value dictionary."""
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── Analytics ────────────────────────────────────────────────────────

    def get_analytics(self, camera_id: str | None = None) -> dict:
        """
        Calculates time-series and categorical analytics:
        - Daily trends for the last 7 days
        - Hourly distribution (peak kitchen violation hours)
        - Per-camera distribution
        - Pest vs Hygiene ratio
        """
        conn = self._get_conn()
        base_where = "WHERE 1=1"
        params: list = []
        if camera_id is not None:
            base_where += " AND camera_id = ?"
            params.append(camera_id)

        # Daily counts for recent days
        daily_rows = conn.execute(
            f"""SELECT substr(timestamp, 1, 10) as day, COUNT(*) as cnt
               FROM violations {base_where}
               GROUP BY day ORDER BY day DESC LIMIT 14""",
            params,
        ).fetchall()
        daily = {r["day"]: r["cnt"] for r in reversed(daily_rows)}

        # Hourly distribution (00 to 23)
        hourly_rows = conn.execute(
            f"""SELECT substr(timestamp, 12, 2) as hour, COUNT(*) as cnt
               FROM violations {base_where}
               GROUP BY hour ORDER BY hour ASC""",
            params,
        ).fetchall()
        hourly = {f"{i:02d}:00": 0 for i in range(24)}
        for r in hourly_rows:
            if r["hour"] and r["hour"].isdigit():
                h_key = f"{int(r['hour']):02d}:00"
                hourly[h_key] = r["cnt"]

        # Per camera distribution
        cam_rows = conn.execute(
            """SELECT v.camera_id, COALESCE(c.name, v.camera_id) as cam_name, COUNT(*) as cnt
               FROM violations v
               LEFT JOIN cameras c ON v.camera_id = c.id
               GROUP BY v.camera_id ORDER BY cnt DESC"""
        ).fetchall()
        by_camera = {r["cam_name"] or "Unknown": r["cnt"] for r in cam_rows}

        # Acknowledged vs unacknowledged
        ack_count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM violations {base_where} AND acknowledged = 1",
            params,
        ).fetchone()["cnt"]

        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM violations {base_where}", params
        ).fetchone()["cnt"]

        return {
            "daily": daily,
            "hourly": hourly,
            "by_camera": by_camera,
            "total": total,
            "acknowledged": ack_count,
            "unacknowledged": total - ack_count,
        }
