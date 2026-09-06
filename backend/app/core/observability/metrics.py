"""Prometheus metrics definitions."""
from __future__ import annotations

from prometheus_client import Counter

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route"]
)
http_request_duration_seconds = Counter(
    "http_request_duration_seconds", "HTTP request duration", ["method", "route"]
)
llm_calls_total = Counter("llm_calls_total", "Total LLM calls", ["model"])
llm_call_duration_seconds = Counter(
    "llm_call_duration_seconds", "LLM call duration", ["model"]
)
rag_retrievals_total = Counter("rag_retrievals_total", "RAG retrievals")
