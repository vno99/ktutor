from __future__ import annotations

"""Prometheus /metrics endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.observability.metrics import (  # noqa: F401
    http_request_duration_seconds,
    http_requests_total,
    llm_call_duration_seconds,
    llm_calls_total,
    rag_retrievals_total,
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
