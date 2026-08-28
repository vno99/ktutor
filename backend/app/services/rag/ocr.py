"""Multimodal OCR client (DeepSeek-OCR-2, see ADR 008).

The local service exposes a single ``/v1/ocr`` endpoint that accepts a base64
image (or a PDF) and returns a JSON payload of the form::

    {
        "transcription": "...",
        "type": "texte|mathematique|mixte",
        "confidence": 0.91,
        "has_math": false
    }

The client retries once with a stricter prompt if the first response is not
JSON, and rejects results with ``confidence < LOW_CONFIDENCE_THRESHOLD`` so
the upload pipeline can surface them as ``manual_review_needed``.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

LOW_CONFIDENCE_THRESHOLD = 0.5
"""Below this, the transcription is considered unreliable and rejected."""

DEFAULT_TIMEOUT = 60.0

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class OcrResult(BaseModel):
    """Outcome of an OCR call.

    ``ok=False`` means the OCR service responded but the result is not
    trustworthy; the upload pipeline should treat this as a refusal (and
    surface ``manual_review_needed`` to the user).
    """

    ok: bool
    transcription: str = ""
    confidence: float = 0.0
    reason: Optional[str] = None
    ocr_type: str = ""
    has_math: bool = False


class OcrError(RuntimeError):
    """Raised when the OCR service is unreachable or returns garbage."""


class MultimodalOcr:
    """HTTP client for the local DeepSeek-OCR-2 service.

    The client is intentionally simple: we never cache responses, never
    batch, never stream. The upload pipeline calls ``transcribe_image`` once
    per uploaded image.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8500",
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    def transcribe_image(self, image_path: str) -> OcrResult:
        """Transcribe a single image (or PDF) into text + confidence."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier OCR introuvable: {image_path}")

        data_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        prompt = _build_prompt()
        payload = {"image_b64": data_b64, "prompt": prompt}

        last_error: Optional[Exception] = None
        for attempt in range(2):
            response_text = self._post(payload)
            parsed = _try_parse_json(response_text)
            if parsed is None:
                # Retry once with a stricter prompt that asks for JSON only.
                payload["prompt"] = _build_strict_prompt()
                last_error = OcrError("Réponse OCR non-JSON")
                continue
            return _result_from_parsed(parsed)
        # Both attempts failed to produce JSON.
        raise OcrError(f"OCR n'a pas renvoyé de JSON exploitable: {last_error}")

    def _post(self, payload: dict[str, Any]) -> str:
        url = f"{self._base_url}/v1/ocr"
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            resp = client.post(url, json=payload)
        if resp.status_code != 200:
            raise OcrError(f"OCR HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.text


def _build_prompt() -> str:
    return (
        "Analyse l'image et renvoie UNIQUEMENT un objet JSON avec les clés: "
        "transcription (string), type (texte|mathematique|mixte), "
        "confidence (float entre 0 et 1), has_math (bool). Pas de prose, "
        "pas de markdown."
    )


def _build_strict_prompt() -> str:
    return (
        "Renvoie STRICTEMENT un objet JSON valide, sans aucune prose autour: "
        '{"transcription": "...", "type": "texte", "confidence": 0.0, "has_math": false}'
    )


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction.

    DeepSeek-OCR-2 sometimes wraps the JSON in a markdown fence or in
    a short preamble. We first try ``json.loads`` on the trimmed text,
    then fall back to a regex search for the first ``{...}`` block.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        # Strip markdown fences
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        pass
    match = _JSON_RE.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError):
        return None


def _result_from_parsed(parsed: dict[str, Any]) -> OcrResult:
    """Build an :class:`OcrResult` from a parsed JSON payload, applying the confidence gate."""
    transcription = str(parsed.get("transcription", "")).strip()
    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    ocr_type = str(parsed.get("type", ""))
    has_math = bool(parsed.get("has_math", False))

    if not transcription:
        return OcrResult(ok=False, reason="empty_transcription")
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return OcrResult(
            ok=False,
            transcription=transcription,
            confidence=confidence,
            reason="low_confidence",
            ocr_type=ocr_type,
            has_math=has_math,
        )
    return OcrResult(
        ok=True,
        transcription=transcription,
        confidence=confidence,
        ocr_type=ocr_type,
        has_math=has_math,
    )
