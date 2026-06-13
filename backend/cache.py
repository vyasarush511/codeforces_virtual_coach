from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _setup(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache_entries(expires_at)")

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            value, expires_at = row
            if expires_at < now:
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                return None
            return json.loads(value)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        payload = json.dumps(value, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries(key, value, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (key, payload, now + ttl_seconds, now),
            )

    def stats(self) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM cache_entries WHERE expires_at >= ?", (now,)).fetchone()
            stale = conn.execute("SELECT COUNT(*) FROM cache_entries WHERE expires_at < ?", (now,)).fetchone()
        return {
            "entries": int(row[0] if row else 0),
            "stale_entries": int(stale[0] if stale else 0),
            "path": str(self.path),
        }

    def purge_expired(self) -> int:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM cache_entries WHERE expires_at < ?", (now,))
            return cur.rowcount

