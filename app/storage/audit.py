"""SQLite audit log — lưu input, rule matched, output, lý do."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.rules.engine import Document

DB_PATH = Path(__file__).resolve().parent / "audit.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            job_id TEXT PRIMARY KEY,
            created_at TEXT,
            so_hieu TEXT,
            co_quan_ban_hanh TEXT,
            trich_yeu TEXT,
            han_xu_ly TEXT,
            assignments TEXT,
            confidence REAL,
            reason TEXT,
            matched_rules TEXT,
            needs_review INTEGER,
            degraded INTEGER,
            tier TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def log(job_id: str, doc: Document, result: Any) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_log
        (job_id, created_at, so_hieu, co_quan_ban_hanh, trich_yeu, han_xu_ly,
         assignments, confidence, reason, matched_rules, needs_review, degraded, tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            datetime.now().isoformat(timespec="seconds"),
            doc.so_hieu,
            doc.co_quan_ban_hanh,
            doc.trich_yeu,
            doc.han_xu_ly.isoformat() if doc.han_xu_ly else None,
            json.dumps(result.assignments, ensure_ascii=False),
            result.confidence,
            result.reason,
            json.dumps(result.matched_rules, ensure_ascii=False),
            int(result.needs_review),
            int(result.degraded),
            result.tier,
        ),
    )
    conn.commit()
    conn.close()
