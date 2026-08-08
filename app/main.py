"""FastAPI entrypoint — server AI local cho AI Document Router.

Chạy:  uvicorn app.main:app --host 127.0.0.1 --port 8000
Docs:  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings

app = FastAPI(
    title="AI Document Router — Server AI local",
    description=(
        "Định tuyến văn bản đến cho Sở Nông nghiệp và Môi trường tỉnh Gia Lai.\n"
        "Core model: deepseek-reasoner (fallback rule engine deterministic)."
    ),
    version="0.1.0",
)
app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "ai-document-router",
        "docs": "/docs",
        "health": "/health",
        "model": settings.DEEPSEEK_MODEL,
        "llm_available": settings.llm_available,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
