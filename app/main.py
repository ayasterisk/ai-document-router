"""FastAPI entrypoint."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.orchestrator.harness import Harness, HttpInferenceClient, MockInferenceClient
from app.rules.engine import RuleEngine
from app.storage.audit import init_db

RULES_PATH = Path(__file__).resolve().parent / "rules" / "rules.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    engine = RuleEngine(RULES_PATH)
    mode = os.getenv("HARNESS_TOOL_MODE", "auto")

    inference_url = os.getenv("INFERENCE_SERVER_URL")
    if inference_url:
        client = HttpInferenceClient(inference_url)
    else:
        client = MockInferenceClient()

    app.state.engine = engine
    app.state.harness = Harness(engine=engine, client=client, mode=mode)
    yield


app = FastAPI(title="AI Document Router — SoNNMT", lifespan=lifespan)
app.include_router(router)
