"""FastAPI contract for the department's existing Tampermonkey client."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Security,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.security import APIKeyHeader

from app.jobs import IdempotencyConflict, QueueFull
from app.models.schema import ROLES, ClassifyResponse, Feedback, JobStatus

router = APIRouter()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def principal(
    request: Request, x_api_key: Annotated[str | None, Security(api_key_header)] = None
):
    if x_api_key:
        for owner, token in request.app.state.settings.api_keys.items():
            if hmac.compare_digest(x_api_key.encode(), token.encode()):
                return owner
    raise HTTPException(401, "invalid_api_key")


Owner = Annotated[str, Depends(principal)]


def job_row(request, job_id, owner):
    row = request.app.state.store.get(job_id, owner)
    if not row:
        raise HTTPException(404, "job_not_found")
    return row


def status(row):
    return JobStatus(
        job_id=row["id"],
        status=row["status"],
        result=json.loads(row["result"]) if row["result"] else None,
        error=row["error"],
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request, owner: Owner):
    try:
        request.app.state.store.ping()
        if request.app.state.manager.closed:
            raise RuntimeError
    except (sqlite3.Error, RuntimeError):
        raise HTTPException(503, "not_ready")
    return {
        "status": "ready",
        "department": "SoNNMT",
        "rules_version": request.app.state.engine.version,
        "rules_sha256": request.app.state.engine.fingerprint,
        "directory_version": request.app.state.directory.version,
        "inference_configured": bool(os.getenv("INFERENCE_SERVER_URL")),
        "policy": "human_confirmation_required",
    }


@router.get("/v1/directory")
def directory(request: Request, owner: Owner):
    d = request.app.state.directory
    return {"version": d.version, "department": "SoNNMT", "recipients": d.entries}


async def receive(request, document_id, received_on, text, files, file):
    s = request.app.state.settings
    if file and files:
        raise HTTPException(422, "use_file_or_files")
    uploaded = files or ([file] if file else [])
    if bool(text and text.strip()) == bool(uploaded):
        raise HTTPException(422, "provide_text_or_pdf_files_exclusively")
    if len(uploaded) > s.max_files:
        raise HTTPException(413, "file_count_limit_exceeded")
    if text and len(text) > s.max_text_chars:
        raise HTTPException(413, "text_limit_exceeded")
    items = []
    total = 0
    try:
        for upload in uploaded:
            chunks = []
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > s.max_upload_bytes:
                    raise HTTPException(413, "upload_limit_exceeded")
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data.lstrip().startswith(b"%PDF-"):
                raise HTTPException(415, "pdf_required")
            items.append(
                {
                    "name": (upload.filename or "document.pdf")[:200],
                    "base64": base64.b64encode(data).decode(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    finally:
        for upload in uploaded:
            await upload.close()
    content = {"text": text or "", "files": [item["sha256"] for item in items]}
    digest = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return {
        "document_id": document_id,
        "received_on": (
            received_on or datetime.now(timezone(timedelta(hours=7))).date()
        ).isoformat(),
        "input_sha256": digest,
        "text": text or "",
        "files": items,
    }


@router.post("/v1/jobs", response_model=JobStatus, status_code=202)
async def create_job(
    request: Request,
    owner: Owner,
    document_id: Annotated[str, Form(min_length=1, max_length=200)],
    received_on: Annotated[date | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    payload = await receive(request, document_id, received_on, text, files, file)
    try:
        job_id = await run_in_threadpool(
            request.app.state.manager.submit, payload, owner, idempotency_key
        )
    except QueueFull:
        raise HTTPException(429, "queue_full", headers={"Retry-After": "5"})
    except IdempotencyConflict:
        raise HTTPException(409, "idempotency_key_conflict")
    row = await run_in_threadpool(job_row, request, job_id, owner)
    return status(row)


@router.get("/v1/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, request: Request, owner: Owner):
    return status(job_row(request, job_id, owner))


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    request: Request,
    owner: Owner,
    document_id: Annotated[str, Form(min_length=1, max_length=200)] = "legacy",
    received_on: Annotated[date | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """Compatibility endpoint. Prefer jobs for PDF/OCR to avoid client timeouts."""
    job = await create_job(
        request, owner, document_id, received_on, text, None, file, None
    )
    while job.status in ("queued", "running"):
        await asyncio.sleep(0.1)
        job = status(await run_in_threadpool(job_row, request, job.job_id, owner))
    if job.status == "failed":
        raise HTTPException(422, job.error)
    return job.result


@router.post("/v1/jobs/{job_id}/feedback", status_code=201)
def feedback(
    job_id: str,
    body: Feedback,
    request: Request,
    owner: Owner,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    payload = body.model_dump(mode="json")
    if idempotency_key:
        previous = request.app.state.store.find_feedback(owner, idempotency_key)
        if previous:
            if previous["job_id"] != job_id or json.loads(previous["payload"]) != payload:
                raise HTTPException(409, "feedback_idempotency_key_conflict")
            return {
                "feedback_id": previous["id"],
                "job_id": job_id,
                "decision": body.decision,
                "recorded": True,
                "dispatch_performed": False,
            }
    row = job_row(request, job_id, owner)
    if row["status"] != "completed":
        raise HTTPException(409, "job_not_completed")
    result = json.loads(row["result"])
    if any(
        getattr(body, key) != result[key]
        for key in ("document_id", "input_sha256", "rules_sha256")
    ):
        raise HTTPException(409, "document_or_result_mismatch")
    if (
        result["rules_sha256"] != request.app.state.engine.fingerprint
        or result["directory_version"] != request.app.state.directory.version
    ):
        raise HTTPException(409, "configuration_changed")
    final = body.final
    if body.decision == "rejected":
        if final is not None:
            raise HTTPException(422, "rejected_decision_has_no_final")
    else:
        if final is None or not final.don_vi_xu_ly_chinh:
            raise HTTPException(422, "final_primary_recipient_required")
        for role in ROLES:
            if any(
                value not in request.app.state.directory.by_id
                for value in getattr(final, role)
            ):
                raise HTTPException(422, "unknown_recipient_id")
        if body.decision == "accepted":
            expected = {
                role: [r["id"] for r in result["recipients"][role]] for role in ROLES
            }
            if (
                any(set(getattr(final, role)) != set(expected[role]) for role in ROLES)
                or final.han_thuc_hien != result["han_thuc_hien"]
                or body.do_khan != result["do_khan"]
            ):
                raise HTTPException(422, "use_edited_for_changed_decision")
    feedback_id = uuid.uuid4().hex
    try:
        request.app.state.store.feedback(
            feedback_id, job_id, owner, payload, idempotency_key
        )
    except sqlite3.IntegrityError:
        # Another request may have won the same idempotency key between the
        # lookup above and the insert. Reconcile with the durable row.
        previous = request.app.state.store.find_feedback(owner, idempotency_key)
        if (
            not previous
            or previous["job_id"] != job_id
            or json.loads(previous["payload"]) != payload
        ):
            raise HTTPException(409, "feedback_idempotency_key_conflict")
        feedback_id = previous["id"]
    return {
        "feedback_id": feedback_id,
        "job_id": job_id,
        "decision": body.decision,
        "recorded": True,
        "dispatch_performed": False,
    }
