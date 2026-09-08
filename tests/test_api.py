"""API integration tests including real worker subprocesses and isolated SQLite."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TEXT = "UBND tỉnh Gia Lai\nSố: 12/UBND-NNMT\nGia Lai, ngày 8 tháng 9 năm 2026\nCÔNG VĂN\nV/v xây dựng công trình thủy lợi\nKính gửi: Sở Nông nghiệp và Môi trường\nĐề nghị hoàn thành trước ngày 10/09/2026."


class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "HARNESS_TOOL_MODE": "off",
                "INFERENCE_SERVER_URL": "",
                "OCR_PROVIDER": "none",
            },
        )
        self.env.start()
        self.settings = Settings(
            api_keys={"alice": "a" * 32, "bob": "b" * 32},
            db_path=Path(self.tmp.name) / "test.db",
            allowed_origins=["https://office.example.vn"],
        )
        self.app = create_app(self.settings)
        self.ctx = TestClient(self.app)
        self.client = self.ctx.__enter__()
        self.auth = {"X-API-Key": "a" * 32}

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.env.stop()
        self.tmp.cleanup()

    def submit(self, text=TEXT, key=None):
        headers = {**self.auth, **({"Idempotency-Key": key} if key else {})}
        return self.client.post(
            "/v1/jobs",
            headers=headers,
            data={"document_id": "doc-12", "received_on": "2026-09-08", "text": text},
        )

    def complete(self, job_id):
        until = time.monotonic() + 20
        while time.monotonic() < until:
            r = self.client.get("/v1/jobs/" + job_id, headers=self.auth)
            self.assertEqual(r.status_code, 200)
            if r.json()["status"] not in ("queued", "running"):
                return r.json()
            time.sleep(0.03)
        self.fail("worker did not complete")

    def test_health_and_auth(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/v1/directory").status_code, 401)
        self.assertEqual(self.client.get("/ready", headers=self.auth).status_code, 200)

    def test_text_subprocess_result_and_directory(self):
        r = self.submit()
        self.assertEqual(r.status_code, 202)
        job = self.complete(r.json()["job_id"])
        self.assertEqual(job["status"], "completed", job)
        result = job["result"]
        self.assertEqual(result["matched_rules"], ["VI.1"])
        self.assertEqual(result["han_thuc_hien"], "2026-09-10")
        self.assertEqual(result["do_khan"], "thuong")
        self.assertTrue(result["requires_confirmation"])
        ids = {
            e["id"]
            for e in self.client.get("/v1/directory", headers=self.auth).json()[
                "recipients"
            ]
        }
        self.assertTrue(
            all(e["id"] in ids for e in result["recipients"]["don_vi_xu_ly_chinh"])
        )

    def test_owner_isolation(self):
        r = self.submit()
        job_id = r.json()["job_id"]
        self.assertEqual(
            self.client.get(
                "/v1/jobs/" + job_id, headers={"X-API-Key": "b" * 32}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/v1/jobs/" + job_id + "/feedback",
                headers={"X-API-Key": "b" * 32},
                json={
                    "document_id": "doc-12",
                    "input_sha256": "x",
                    "rules_sha256": "x",
                    "decision": "rejected",
                },
            ).status_code,
            404,
        )

    def test_idempotency(self):
        first = self.submit(key="request-1")
        second = self.submit(key="request-1")
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        self.assertEqual(
            self.submit(TEXT + " changed", key="request-1").status_code, 409
        )

    def test_feedback_stale_unknown_and_accepted(self):
        result = self.complete(self.submit().json()["job_id"])["result"]
        body = {k: result[k] for k in ("document_id", "input_sha256", "rules_sha256")}
        body.update(
            decision="accepted",
            do_khan=result["do_khan"],
            final={
                **{
                    role: [r["id"] for r in refs]
                    for role, refs in result["recipients"].items()
                },
                "han_thuc_hien": result["han_thuc_hien"],
            },
        )
        url = "/v1/jobs/" + result["job_id"] + "/feedback"
        self.assertEqual(
            self.client.post(
                url, headers=self.auth, json={**body, "document_id": "other"}
            ).status_code,
            409,
        )
        wrong = json.loads(json.dumps(body))
        wrong["final"]["don_vi_xu_ly_chinh"] = ["not-in-directory"]
        self.assertEqual(
            self.client.post(url, headers=self.auth, json=wrong).status_code, 422
        )
        good = self.client.post(url, headers=self.auth, json=body)
        self.assertEqual(good.status_code, 201, good.text)
        self.assertFalse(good.json()["dispatch_performed"])

    def test_inputs_and_limits(self):
        self.assertEqual(
            self.client.post(
                "/v1/jobs", headers=self.auth, data={"document_id": "d"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/v1/jobs",
                headers=self.auth,
                data={"document_id": "d"},
                files={"file": ("a.pdf", b"not pdf")},
            ).status_code,
            415,
        )
        self.assertEqual(
            self.client.post(
                "/v1/jobs",
                headers=self.auth,
                data={"document_id": "d", "text": "abc"},
                files={"file": ("a.pdf", b"%PDF-1.7")},
            ).status_code,
            422,
        )
        self.settings.max_upload_bytes = 10
        r = self.client.post(
            "/v1/jobs",
            headers=self.auth,
            data={"document_id": "d"},
            files={"file": ("a.pdf", b"%PDF-1.7" + b"x" * 20)},
        )
        self.assertEqual(r.status_code, 413)

    def test_cors(self):
        r = self.client.options(
            "/v1/jobs",
            headers={
                "Origin": "https://office.example.vn",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-API-Key,Idempotency-Key",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.headers["access-control-allow-origin"], "https://office.example.vn"
        )
        r = self.client.options(
            "/v1/jobs",
            headers={
                "Origin": "https://other.example.vn",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", r.headers)

    def test_unknown_text_does_not_use_mock(self):
        result = self.complete(self.submit("Nội dung không rõ ràng").json()["job_id"])[
            "result"
        ]
        self.assertEqual(result["don_vi_xu_ly_chinh"], [])
        self.assertTrue(result["needs_review"])
        self.assertIsNone(result["han_thuc_hien"])

    def test_legacy_endpoint(self):
        r = self.client.post(
            "/classify",
            headers=self.auth,
            data={"text": TEXT, "received_on": "2026-09-08"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["matched_rules"], ["VI.1"])

    def test_real_pdf_worker(self):
        from test_pdf import VALID, pdf_bytes

        r = self.client.post(
            "/v1/jobs",
            headers=self.auth,
            data={"document_id": "pdf-1"},
            files={"file": ("a.pdf", pdf_bytes([VALID]))},
        )
        job = self.complete(r.json()["job_id"])
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(job["result"]["extraction"]["files"][0]["page_count"], 1)
        self.assertTrue(job["result"]["needs_review"])

    def test_chunked_body_limit(self):
        boundary = "test-boundary"
        data = (
            b'--test-boundary\r\nContent-Disposition: form-data; name="text"\r\n\r\n'
            + b"x" * (self.settings.max_upload_bytes + 1024 * 1024 + 1)
            + b"\r\n--test-boundary--\r\n"
        )
        r = self.client.post(
            "/v1/jobs",
            headers={
                **self.auth,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
            },
            content=iter([data]),
        )
        self.assertEqual(r.status_code, 413, r.text)

    def test_second_instance_cannot_reset_jobs(self):
        with (
            self.assertRaisesRegex(RuntimeError, "workers 1"),
            TestClient(create_app(self.settings)),
        ):
            pass

    def test_bad_pdf_job_fails(self):
        r = self.client.post(
            "/v1/jobs",
            headers=self.auth,
            data={"document_id": "bad"},
            files={"file": ("a.pdf", b"%PDF-1.7 broken")},
        )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.complete(r.json()["job_id"])["error"], "invalid_pdf")


if __name__ == "__main__":
    unittest.main()
