"""Bounded queue, durable statuses, per-job subprocess timeout. Run one ASGI worker."""

import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.config import ROOT

logger = logging.getLogger(__name__)


def _kill_process_tree(process):
    """Kill a process and its descendants (Tesseract/OCR children) on timeout."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.kill()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        logger.warning("kill_process_tree failed: %s", exc)


class QueueFull(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class JobManager:
    def __init__(self, settings, store, engine, directory):
        self.settings, self.store, self.engine, self.directory = (
            settings,
            store,
            engine,
            directory,
        )
        self.executor = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="router-job"
        )
        self.slots = threading.BoundedSemaphore(settings.max_pending)
        self.lock = threading.Lock()
        self.futures = {}
        self.closed = False

    def submit(self, payload, owner, key=None):
        identity = {
            k: payload[k] for k in ("document_id", "input_sha256", "received_on")
        }
        identity.update(
            rules_sha256=self.engine.fingerprint,
            directory_version=self.directory.version,
        )
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()
        with self.lock:
            old = self.store.find_key(owner, key)
            if old:
                if old["fingerprint"] != fingerprint:
                    raise IdempotencyConflict
                return old["id"]
            if self.closed or not self.slots.acquire(blocking=False):
                raise QueueFull
            job_id = uuid.uuid4().hex
            payload = {
                **payload,
                "job_id": job_id,
                "rules_path": str(self.settings.rules_path),
                "directory_path": str(self.settings.directory_path),
                "rules_sha256": self.engine.fingerprint,
                "directory_version": self.directory.version,
                "max_pages": self.settings.max_pages,
                "max_text_chars": self.settings.max_text_chars,
            }
            try:
                self.store.create(job_id, owner, key, fingerprint, identity)
                future = self.executor.submit(self._execute, payload)
                self.futures[job_id] = future
            except Exception:
                self.slots.release()
                raise
        future.add_done_callback(lambda f: self._finished(job_id, f))
        return job_id

    def _finished(self, job_id, future):
        try:
            if future.cancelled():
                self.store.finish(job_id, "failed", error="server_stopping")
        finally:
            self.slots.release()
            with self.lock:
                self.futures.pop(job_id, None)

    def _execute(self, payload):
        job_id = payload["job_id"]
        try:
            self.store.finish(job_id, "running")
            process = subprocess.Popen(
                [sys.executable, "-m", "app.worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                cwd=ROOT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            try:
                stdout, _ = process.communicate(
                    input=json.dumps(payload, ensure_ascii=False),
                    timeout=self.settings.job_timeout,
                )
            except subprocess.TimeoutExpired:
                _kill_process_tree(process)
                self.store.finish(job_id, "failed", error="job_timeout")
                return
            if process.returncode != 0:
                raise RuntimeError("worker_failed")
            output = json.loads(stdout)
            if "error" in output:
                self.store.finish(job_id, "failed", error=output["error"])
            else:
                self.store.finish(
                    job_id,
                    "completed",
                    result=output["result"],
                    audit_text=output.get("audit_text"),
                )
        except Exception:  # noqa: BLE001 - isolate provider/job failures and record status
            self.store.finish(job_id, "failed", error="processing_failed")

    def close(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
