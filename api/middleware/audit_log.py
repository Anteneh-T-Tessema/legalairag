from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Logs every API request/response for compliance and debugging.
    Assigns a unique request_id to each request for traceability.
    Sensitive headers (Authorization) are redacted.
    """

    async def dispatch(self, request: Request, call_next: any) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "api_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_host=request.client.host if request.client else "unknown",
        )

        response.headers["X-Request-Id"] = request_id
        structlog.contextvars.clear_contextvars()
        return response
