import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import Settings
from app.jobs import JobManager, QueueFull
from app.models.directory import Directory
from app.rules.engine import RuleEngine
from app.storage.audit import AuditStore


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            db_path=Path(self.tmp.name) / "test.db",
            max_workers=1,
            max_pending=1,
            job_timeout=1,
        )
        self.store = AuditStore(self.settings.db_path)
        self.store.init()
        self.manager = JobManager(
            self.settings,
            self.store,
            RuleEngine(self.settings.rules_path),
            Directory(self.settings.directory_path),
        )
        self.payload = {
            "document_id": "d",
            "input_sha256": "abc",
            "received_on": "2026-09-08",
            "text": "hello",
        }

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def wait_done(self, job_id):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            row = self.store.get(job_id, "alice")
            if row["status"] not in ("queued", "running"):
                return row
            time.sleep(0.01)
        self.fail("job never completed")

    def test_timeout_is_persisted_and_capacity_recovers(self):
        fake_process = Mock()
        fake_process.communicate.side_effect = subprocess.TimeoutExpired("worker", 1)
        with patch("app.jobs.subprocess.Popen", return_value=fake_process), patch(
            "app.jobs._kill_process_tree"
        ) as kill_mock, patch("app.jobs._reap_process") as reap_mock:
            job = self.manager.submit(self.payload, "alice")
            row = self.wait_done(job)
        self.assertEqual(row["error"], "job_timeout")
        kill_mock.assert_called_once_with(fake_process)
        reap_mock.assert_called_once_with(fake_process)
        until = time.monotonic() + 1
        while self.manager.futures and time.monotonic() < until:
            time.sleep(0.01)
        self.assertFalse(self.manager.futures)

    def test_real_process_timeout(self):
        self.settings.job_timeout = 0.001
        job = self.manager.submit(self.payload, "alice")
        self.assertEqual(self.wait_done(job)["error"], "job_timeout")

    def test_backpressure(self):
        entered = threading.Event()
        release = threading.Event()

        def communicate(*args, **kwargs):
            entered.set()
            release.wait(3)
            return (json.dumps({"error": "invalid_pdf"}), "")

        fake_process = Mock()
        fake_process.communicate.side_effect = communicate
        fake_process.returncode = 0

        with patch("app.jobs.subprocess.Popen", return_value=fake_process):
            job = self.manager.submit(self.payload, "alice")
            self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(QueueFull):
                    self.manager.submit(self.payload, "alice")
            finally:
                release.set()
            self.wait_done(job)

    def test_recovery_keeps_completed_jobs(self):
        self.store.create("queued", "alice", None, "hash", {})
        self.store.create("completed", "alice", None, "hash", {})
        self.store.finish(
            "completed", "completed", result={"ok": True}, audit_text="full document"
        )
        self.store.recover()
        self.assertEqual(self.store.get("queued", "alice")["error"], "server_restarted")
        self.assertEqual(self.store.get("completed", "alice")["status"], "completed")
        self.assertEqual(
            self.store.get("completed", "alice")["audit_text"], "full document"
        )

    def test_migration_preserves_config_history(self):
        import sqlite3

        # Recreate an OLD-schema table (PK = rules_sha256) with legacy rows.
        conn = sqlite3.connect(self.settings.db_path)
        conn.execute("DROP TABLE router_rule_versions")
        conn.execute(
            "CREATE TABLE router_rule_versions ("
            "rules_sha256 TEXT PRIMARY KEY, rules_version TEXT NOT NULL, rules_text TEXT NOT NULL,"
            "directory_sha256 TEXT NOT NULL, directory_text TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO router_rule_versions VALUES (?,?,?,?,?)",
            ("rules_a", "1.0", "rules text a", "dir_a", "directory text a"),
        )
        conn.execute(
            "INSERT INTO router_rule_versions VALUES (?,?,?,?,?)",
            ("rules_b", "1.0", "rules text b", "dir_b", "directory text b"),
        )
        conn.commit()
        conn.close()
        self.store.init()
        with self.store.connection() as c:
            rows = c.execute(
                "SELECT rules_sha256, directory_sha256, configuration_fingerprint "
                "FROM router_rule_versions ORDER BY rules_sha256"
            ).fetchall()
        self.assertEqual([r["rules_sha256"] for r in rows], ["rules_a", "rules_b"])
        self.assertEqual([r["directory_sha256"] for r in rows], ["dir_a", "dir_b"])
        self.assertTrue(all(r["configuration_fingerprint"] for r in rows))


if __name__ == "__main__":
    unittest.main()
