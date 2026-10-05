"""Thin authenticated proxy in front of Ollama's OpenAI-compatible API.

Hostinger calls this over the private link (WireGuard) or a firewall-whitelisted
public port. Ollama itself stays bound to 127.0.0.1:11434 and never touches the
internet. The routing backend only needs /v1/chat/completions; /v1/models and
/health are for debugging and readiness checks.
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
API_KEY = os.getenv("AI_API_KEY", "")

app = FastAPI(title="Ollama auth proxy")


def _authorized(authorization: str | None) -> bool:
    return bool(API_KEY) and authorization == f"Bearer {API_KEY}"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request, authorization: str | None = Header(default=None)
):
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    async with httpx.AsyncClient(timeout=600) as client:
        response = await client.post(
            f"{OLLAMA_URL}/v1/chat/completions", json=body
        )
    if response.status_code >= 400:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream", "detail": response.text[:2000]},
        )
    return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)):
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{OLLAMA_URL}/v1/models")
    return JSONResponse(status_code=response.status_code, content=response.json())
