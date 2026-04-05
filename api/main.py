from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.audit_log import AuditLogMiddleware
from api.routers import documents, search
from api.routers.auth_router import router as auth_router
from config.logging import configure_logging
from config.settings import settings

configure_logging(settings.log_level)

app = FastAPI(
    title="IndyLeg — Indiana Legal RAG Platform",
    version="0.1.0",
    description="AI-powered legal research and document intelligence for Indiana courts.",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(AuditLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
