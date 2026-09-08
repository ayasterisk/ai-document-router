"""ASGI app with bounded uploads and authenticated, owner-scoped jobs."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.routes import router
from app.config import Settings
from app.jobs import JobManager
from app.models.directory import Directory
from app.rules.engine import RuleEngine
from app.storage.audit import AuditStore


class BodyTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "request_body_too_large")


class BodyLimitMiddleware:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = self.limit + 1
        if length > self.limit:
            return await JSONResponse({"detail": "request_body_too_large"}, 413)(
                scope, receive, send
            )
        total = 0
        started = False

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.limit:
                raise BodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "request_body_too_large"}, 413)(
                    scope, receive, send
                )


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        engine = RuleEngine(settings.rules_path)
        directory = Directory(settings.directory_path)
        missing = set(engine.recipient_names()) - set(directory.by_name)
        if missing:
            raise ValueError(
                "Directory missing rule recipients: " + ", ".join(sorted(missing))
            )
        store = AuditStore(settings.db_path)
        with store.exclusive():
            store.init()
            store.save_configuration(engine, settings.directory_path, directory)
            store.recover()
            store.purge(settings.retention_days)
            manager = JobManager(settings, store, engine, directory)
            app.state.settings, app.state.engine, app.state.directory = (
                settings,
                engine,
                directory,
            )
            app.state.store, app.state.manager = store, manager
            try:
                yield
            finally:
                await run_in_threadpool(manager.close)

    app = FastAPI(title="SoNNMT Document Router", version="2.0.0", lifespan=lifespan)
    app.add_middleware(
        BodyLimitMiddleware, limit=settings.max_upload_bytes + 1024 * 1024
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key"],
        expose_headers=["Retry-After"],
    )
    app.include_router(router)
    return app


app = create_app()
