from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from api.middleware.audit_log import AuditLogMiddleware
from api.middleware.metrics import MetricsMiddleware, format_prometheus, get_metrics
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.routers import documents, search
from api.routers.auth_router import router as auth_router
from api.routers.fraud import router as fraud_router
from config.logging import configure_logging
from config.settings import settings

configure_logging(settings.log_level)

app = FastAPI(
    title="IndyLeg — Indiana Legal RAG Platform",
    version="0.2.0",
    description="AI-powered legal research and document intelligence for Indiana courts.",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

# ── Middleware (order matters: outermost first) ───────────────────────────────

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    max_age=600,
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(fraud_router, prefix="/api/v1")


# ── Health & Observability ────────────────────────────────────────────────────


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/metrics", tags=["ops"], response_class=PlainTextResponse)
async def metrics() -> str:
    """Prometheus-compatible metrics endpoint."""
    return format_prometheus()


@app.get("/metrics/json", tags=["ops"])
async def metrics_json() -> dict:
    """JSON metrics for dashboards and monitoring."""
    return get_metrics()
