"""Durable job state and append-only decisions, isolated from legacy audit tables."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def exclusive(self):
        """Prevent a second ASGI worker from resetting active jobs in this database."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(str(self.path) + ".lock", "a+b")  # noqa: SIM115 - released in generator finally
        locked = False
        try:
            try:
                handle.seek(0, 2)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                raise RuntimeError(
                    "Database already in use: run uvicorn with --workers 1"
                ) from exc
            yield
        finally:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS router_jobs (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, idempotency_key TEXT,
              fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, request_meta TEXT NOT NULL, result TEXT, error TEXT,
              UNIQUE(owner,idempotency_key));
            CREATE TABLE IF NOT EXISTS router_rule_versions (
              configuration_fingerprint TEXT PRIMARY KEY, rules_sha256 TEXT NOT NULL, rules_version TEXT NOT NULL,
              rules_text TEXT NOT NULL, directory_sha256 TEXT NOT NULL, directory_text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS router_feedback (
              id TEXT PRIMARY KEY, job_id TEXT NOT NULL, owner TEXT NOT NULL,
              created_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS router_feedback_job ON router_feedback(job_id);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(router_jobs)")}
            if "audit_text" not in columns:
                conn.execute("ALTER TABLE router_jobs ADD COLUMN audit_text TEXT")
            rule_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(router_rule_versions)")
            }
            if "configuration_fingerprint" not in rule_columns:
                # Migrate: old PK was rules_sha256 only, which dropped directory-only changes.
                # Preserve history: rename, recreate, copy with new fingerprint, then drop legacy.
                conn.execute(
                    "ALTER TABLE router_rule_versions RENAME TO router_rule_versions_legacy"
                )
                conn.execute(
                    """
                    CREATE TABLE router_rule_versions (
                      configuration_fingerprint TEXT PRIMARY KEY, rules_sha256 TEXT NOT NULL, rules_version TEXT NOT NULL,
                      rules_text TEXT NOT NULL, directory_sha256 TEXT NOT NULL, directory_text TEXT NOT NULL);
                    """
                )
                legacy = conn.execute(
                    "SELECT rules_sha256, rules_version, rules_text, directory_sha256, directory_text "
                    "FROM router_rule_versions_legacy"
                ).fetchall()
                for row in legacy:
                    fingerprint = hashlib.sha256(
                        (row["rules_sha256"] + row["directory_sha256"]).encode()
                    ).hexdigest()
                    conn.execute(
                        "INSERT OR IGNORE INTO router_rule_versions VALUES (?,?,?,?,?,?)",
                        (
                            fingerprint,
                            row["rules_sha256"],
                            row["rules_version"],
                            row["rules_text"],
                            row["directory_sha256"],
                            row["directory_text"],
                        ),
                    )
                conn.execute("DROP TABLE router_rule_versions_legacy")

    def save_configuration(self, engine, directory_path, directory):
        fingerprint = hashlib.sha256(
            (engine.fingerprint + directory.version).encode()
        ).hexdigest()
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO router_rule_versions VALUES (?,?,?,?,?,?)",
                (
                    fingerprint,
                    engine.fingerprint,
                    engine.version,
                    engine.rules_path.read_text(encoding="utf-8"),
                    directory.version,
                    directory_path.read_text(encoding="utf-8"),
                ),
            )

    def recover(self):
        with self.connection() as conn:
            conn.execute(
                "UPDATE router_jobs SET status='failed',error='server_restarted',updated_at=? WHERE status IN ('queued','running')",
                (now(),),
            )

    def purge(self, days):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connection() as conn:
            conn.execute(
                'DELETE FROM router_feedback WHERE job_id IN (SELECT id FROM router_jobs WHERE status IN ("completed","failed") AND created_at < ?)',
                (cutoff,),
            )
            conn.execute(
                'DELETE FROM router_jobs WHERE status IN ("completed","failed") AND created_at < ?',
                (cutoff,),
            )

    def ping(self):
        with self.connection() as conn:
            conn.execute("SELECT 1").fetchone()

    def find_key(self, owner, key):
        if not key:
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM router_jobs WHERE owner=? AND idempotency_key=?",
                (owner, key),
            ).fetchone()
            return dict(row) if row else None

    def create(self, job_id, owner, key, fingerprint, meta):
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO router_jobs (id,owner,idempotency_key,fingerprint,status,created_at,updated_at,request_meta,result,error) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    owner,
                    key,
                    fingerprint,
                    "queued",
                    now(),
                    now(),
                    json.dumps(meta, ensure_ascii=False),
                    None,
                    None,
                ),
            )

    def get(self, job_id, owner):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM router_jobs WHERE id=? AND owner=?", (job_id, owner)
            ).fetchone()
            return dict(row) if row else None

    def finish(self, job_id, status, result=None, error=None, audit_text=None):
        with self.connection() as conn:
            conn.execute(
                "UPDATE router_jobs SET status=?,updated_at=?,result=?,error=?,audit_text=COALESCE(?,audit_text) WHERE id=?",
                (
                    status,
                    now(),
                    json.dumps(result, ensure_ascii=False) if result else None,
                    error,
                    audit_text,
                    job_id,
                ),
            )

    def feedback(self, feedback_id, job_id, owner, payload):
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO router_feedback VALUES (?,?,?,?,?)",
                (
                    feedback_id,
                    job_id,
                    owner,
                    now(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
