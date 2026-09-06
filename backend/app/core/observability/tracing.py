"""OpenTelemetry tracing setup (console / OTLP)."""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.core.config import get_settings


def setup_tracing() -> TracerProvider:
    provider = TracerProvider()
    settings = get_settings()
    exporter_type = settings.ot_exporter  # console or otlp
    if exporter_type == "otlp":
        exporter = OTLPSpanExporter()
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider
