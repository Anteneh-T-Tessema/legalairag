"""Lightweight request metrics middleware for observability.

Tracks per-endpoint request counts, latencies (p50/p95/p99), and error rates.
Exposes metrics at /metrics in Prometheus text format for easy integration
with CloudWatch Agent, Prometheus, or Datadog.

For production: consider OpenTelemetry or aws-embedded-metrics for richer
CloudWatch integration.  This module provides a zero-dependency baseline.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# ── In-memory metric stores ─────────────────────────────────────────────────

_request_count: dict[str, int] = defaultdict(int)
_error_count: dict[str, int] = defaultdict(int)
_latencies: dict[str, list[float]] = defaultdict(list)

_MAX_LATENCY_SAMPLES = 10_000  # per route; ring-buffer to bound memory


def _record(method: str, path: str, status: int, duration_ms: float) -> None:
    key = f"{method} {path}"
    _request_count[key] += 1
    if status >= 500:
        _error_count[key] += 1
    buf = _latencies[key]
    if len(buf) >= _MAX_LATENCY_SAMPLES:
        buf.pop(0)
    buf.append(duration_ms)


def get_metrics() -> dict[str, Any]:
    """Return a snapshot of current metrics."""
    result: dict[str, Any] = {}
    for key in sorted(_request_count):
        lats = sorted(_latencies.get(key, []))
        n = len(lats)
        result[key] = {
            "requests": _request_count[key],
            "errors": _error_count.get(key, 0),
            "p50_ms": round(lats[n // 2], 2) if n else 0,
            "p95_ms": round(lats[int(n * 0.95)] if n else 0, 2),
            "p99_ms": round(lats[int(n * 0.99)] if n else 0, 2),
        }
    return result


def format_prometheus() -> str:
    """Format metrics in Prometheus exposition format."""
    lines: list[str] = []
    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    for key, count in sorted(_request_count.items()):
        method, path = key.split(" ", 1)
        labels = f'method="{method}",path="{path}"'
        lines.append(f"http_requests_total{{{labels}}} {count}")

    lines.append("# HELP http_errors_total Total HTTP 5xx errors")
    lines.append("# TYPE http_errors_total counter")
    for key, count in sorted(_error_count.items()):
        method, path = key.split(" ", 1)
        labels = f'method="{method}",path="{path}"'
        lines.append(f"http_errors_total{{{labels}}} {count}")

    lines.append("# HELP http_request_duration_ms Request duration in milliseconds")
    lines.append("# TYPE http_request_duration_ms summary")
    for key, lats in sorted(_latencies.items()):
        if not lats:
            continue
        method, path = key.split(" ", 1)
        labels = f'method="{method}",path="{path}"'
        s = sorted(lats)
        n = len(s)
        lines.append(f'http_request_duration_ms{{{labels},quantile="0.5"}} {s[n // 2]:.2f}')
        lines.append(f'http_request_duration_ms{{{labels},quantile="0.95"}} {s[int(n * 0.95)]:.2f}')
        lines.append(f'http_request_duration_ms{{{labels},quantile="0.99"}} {s[int(n * 0.99)]:.2f}')
        lines.append(f"http_request_duration_ms_count{{{labels}}} {n}")

    return "\n".join(lines) + "\n"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record per-route request count, error count, and latency."""

    async def dispatch(self, request: Request, call_next: any) -> Response:  # type: ignore[override]
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Normalize path: strip query string, use route pattern if available
        path = request.url.path
        _record(request.method, path, response.status_code, duration_ms)

        return response
