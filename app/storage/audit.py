"""Audit log — SQLite (demo). Lưu input, rule matched, output, lý do để admin review."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    job_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    pdf_name TEXT,
    pdf_chars INTEGER,
    method TEXT,
    confidence REAL,
    recipients TEXT,
    matched_rules TEXT,
    reasoning TEXT,
    metadata_verified INTEGER,
    needs_human_review INTEGER,
    warning TEXT
);
"""


class AuditStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def insert(self, record: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO audit_log
                   (created_at, job_id, payload, pdf_name, pdf_chars, method,
                    confidence, recipients, matched_rules, reasoning,
                    metadata_verified, needs_human_review, warning)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    record.get("job_id", ""),
                    json.dumps(record.get("payload", {}), ensure_ascii=False),
                    record.get("pdf_name"),
                    record.get("pdf_chars"),
                    record.get("method"),
                    record.get("confidence"),
                    json.dumps(record.get("recipients", []), ensure_ascii=False),
                    json.dumps(record.get("matched_rules", []), ensure_ascii=False),
                    record.get("reasoning", ""),
                    1 if record.get("metadata_verified") else 0,
                    1 if record.get("needs_human_review") else 0,
                    record.get("warning"),
                ),
            )
            return int(cur.lastrowid)

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_log WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None
