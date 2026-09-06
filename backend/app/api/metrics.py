"""Prometheus /metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.core.observability.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    llm_calls_total,
    llm_call_duration_seconds,
    rag_retrievals_total,
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
