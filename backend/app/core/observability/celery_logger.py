"""Celery observability wrapper — ready but no tasks registered yet."""
from __future__ import annotations

from loguru import logger


def init_celery_logger() -> None:
    """Register Celery signal handlers for structured JSON logging.

    No Celery tasks are currently defined in the backend; this wrapper
    is prepared for future stories that introduce tasks (s01 pipeline,
    OCR, evaluation processing, etc.).
    """
    try:
        import celery
        from celery.signals import before_task_publish, after_task_publish, task_failure, task_retry, task_success

        @before_task_publish.connect
        def log_before_task_publish(sender=None, body=None, headers=None, **kwargs) -> None:
            logger.info("Celery task start", extra={"task": sender.name if hasattr(sender, "name") else str(sender), "body_id": str(body) if body else None})

        @after_task_publish.connect
        def log_after_task_publish(sender=None, body=None, result=None, **kwargs) -> None:
            logger.info("Celery task success", extra={"task": sender.name if hasattr(sender, "name") else str(sender)})

        @task_failure.connect
        def log_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
            logger.error("Celery task failure", extra={"task": sender.name if hasattr(sender, "name") else str(sender), "task_id": str(task_id), "exception": str(exception)})

        @task_retry.connect
        def log_task_retry(sender=None, request=None, reason=None, **kwargs) -> None:
            logger.info("Celery task retry", extra={"task": sender.name if hasattr(sender, "name") else str(sender), "reason": str(reason)})

        @task_success.connect
        def log_task_success(sender=None, result=None, **kwargs) -> None:
            logger.info("Celery task completed", extra={"task": sender.name if hasattr(sender, "name") else str(sender)})
    except ImportError:
        # Celery package not installed; wrapper remains import-safe.
        pass
