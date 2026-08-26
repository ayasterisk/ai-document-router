"""SQLite audit log — lưu input, metadata, rule matched, output 4 trường."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

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
            input_text TEXT,
            don_vi_xu_ly_chinh TEXT,
            phoi_hop_xu_ly TEXT,
            lanh_dao_theo_doi TEXT,
            han_thuc_hien TEXT,
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


def log(job_id: str, input_text: str, result: Any) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_log
        (job_id, created_at, input_text, don_vi_xu_ly_chinh, phoi_hop_xu_ly,
         lanh_dao_theo_doi, han_thuc_hien, confidence, reason, matched_rules,
         needs_review, degraded, tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            datetime.now().isoformat(timespec="seconds"),
            input_text[:2000],
            json.dumps(result.don_vi_xu_ly_chinh, ensure_ascii=False),
            json.dumps(result.phoi_hop_xu_ly, ensure_ascii=False),
            json.dumps(result.lanh_dao_theo_doi, ensure_ascii=False),
            result.han_thuc_hien,
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
