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
        with patch("app.jobs.subprocess.Popen", return_value=fake_process):
            job = self.manager.submit(self.payload, "alice")
            row = self.wait_done(job)
        self.assertEqual(row["error"], "job_timeout")
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


if __name__ == "__main__":
    unittest.main()
