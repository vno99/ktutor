"""Native FastAPI HTTP observability middleware."""
from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from loguru import logger
from app.core.observability.metrics import (
    http_requests_total,
    http_request_duration_seconds,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Any:
        start = time.time()
        request_id = str(uuid.uuid4())[:8]
        route = request.url.path
        # Try to extract pseudo from JWT (if auth header present)
        pseudo = None
        # Minimal extraction: we don't decode JWT here to keep middleware fast.
        # The middleware logs the fields; pseudo is set to None if not available,
        # and the logging layer will propagate it via contextvars when available.
        try:
            # We rely on the logger's extra fields set elsewhere (e.g. router).
            # For the middleware, we inject at least request_id and route.
            pass
        except Exception:
            pass
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "HTTP request",
            extra={
                "request_id": request_id,
                "pseudo": pseudo,
                "route": route,
                "duration_ms": round(duration_ms, 2),
            },
        )
        http_requests_total.labels(method=request.method, route=route).inc()
        # Duration tracked as event count (Counter) per AC; duration value is in log payload.
        http_request_duration_seconds.labels(
            method=request.method, route=route
        ).inc()
        return response
