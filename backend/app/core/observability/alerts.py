"""Alert rules and POC console alerting."""
from __future__ import annotations

from loguru import logger

# POC alert thresholds (mirrored in docs/stories.md AC)
ERROR_RATE_THRESHOLD = 0.05  # 5%
LATENCY_P95_THRESHOLD = 5.0  # seconds
CELERY_QUEUE_THRESHOLD = 100


def check_alerts(metrics_snapshot: dict) -> list[str]:
    """POC alert evaluation — log ALERT lines to console."""
    alerts: list[str] = []
    total = metrics_snapshot.get("http_requests_total", 0)
    errors_5xx = metrics_snapshot.get("http_requests_5xx", 0)
    rate_5xx = errors_5xx / total if total > 0 else 0.0
    if rate_5xx > ERROR_RATE_THRESHOLD:
        msg = (
            f"ALERT: 5xx error rate {rate_5xx:.2%} exceeds "
            f"threshold {ERROR_RATE_THRESHOLD:.0%}"
        )
        logger.warning(msg)
        alerts.append(msg)
    p95_latency = metrics_snapshot.get("p95_latency_sec", 0.0)
    if p95_latency > LATENCY_P95_THRESHOLD:
        msg = (
            f"ALERT: p95 latency {p95_latency:.2f}s exceeds "
            f"threshold {LATENCY_P95_THRESHOLD}s"
        )
        logger.warning(msg)
        alerts.append(msg)
    queue_len = metrics_snapshot.get("celery_queue_length", 0)
    if queue_len > CELERY_QUEUE_THRESHOLD:
        msg = (
            f"ALERT: Celery queue length {queue_len} exceeds "
            f"threshold {CELERY_QUEUE_THRESHOLD}"
        )
        logger.warning(msg)
        alerts.append(msg)
    return alerts
