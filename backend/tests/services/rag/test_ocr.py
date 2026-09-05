"""Tests for ``MultimodalOcr`` using ``httpx.MockTransport``.

We never contact a real OCR service: every test wires a ``MockTransport``
that returns a controlled response, so the parsing / confidence / retry
contract is exercised deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.rag.ocr import (
    LOW_CONFIDENCE_THRESHOLD,
    MultimodalOcr,
    OcrError,
)


class _StaticTransport(httpx.BaseTransport):
    """Always returns the same canned response, status and body."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        self.call_count = 0
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        self.last_request = request
        return httpx.Response(self.status_code, content=self.body)


def _make_ocr(transport: httpx.BaseTransport) -> MultimodalOcr:
    return MultimodalOcr(base_url="http://test-ocr", transport=transport)


def _payload(transcription: str, confidence: float, **extra) -> dict:
    return {
        "transcription": transcription,
        "type": "texte",
        "confidence": confidence,
        "has_math": False,
        **extra,
    }


@pytest.fixture()
def small_image(tmp_path: Path) -> Path:
    """A tiny PNG (1x1) is enough — the OCR mock ignores the bytes."""
    from PIL import Image

    p = tmp_path / "img.png"
    Image.new("RGB", (1, 1), color="white").save(p)
    return p


class TestHappyPath:
    def test_returns_ocr_result_for_clean_json(self, small_image: Path) -> None:
        body = json.dumps(_payload("Bonjour le monde", 0.91))
        transport = _StaticTransport(200, body)
        ocr = _make_ocr(transport)
        result = ocr.transcribe_image(str(small_image))
        assert result.ok is True
        assert result.transcription == "Bonjour le monde"
        assert result.confidence == 0.91
        assert transport.call_count == 1

    def test_strips_markdown_fences(self, small_image: Path) -> None:
        body = "```json\n" + json.dumps(_payload("texte", 0.8)) + "\n```"
        transport = _StaticTransport(200, body)
        result = _make_ocr(transport).transcribe_image(str(small_image))
        assert result.ok is True
        assert result.transcription == "texte"

    def test_extracts_json_from_preamble(self, small_image: Path) -> None:
        body = "Here you go:\n" + json.dumps(_payload("abc", 0.7))
        transport = _StaticTransport(200, body)
        result = _make_ocr(transport).transcribe_image(str(small_image))
        assert result.ok is True
        assert result.transcription == "abc"


class TestConfidenceGate:
    def test_low_confidence_yields_not_ok(self, small_image: Path) -> None:
        body = json.dumps(_payload("flou", LOW_CONFIDENCE_THRESHOLD - 0.1))
        result = _make_ocr(_StaticTransport(200, body)).transcribe_image(str(small_image))
        assert result.ok is False
        assert result.reason == "low_confidence"
        assert result.transcription == "flou"  # kept for debugging
        assert result.confidence < LOW_CONFIDENCE_THRESHOLD

    def test_empty_transcription_yields_not_ok(self, small_image: Path) -> None:
        body = json.dumps(_payload("   ", 0.99))
        result = _make_ocr(_StaticTransport(200, body)).transcribe_image(str(small_image))
        assert result.ok is False
        assert result.reason == "empty_transcription"


class TestRetryOnNonJson:
    def test_retry_picks_up_strict_prompt(self, small_image: Path) -> None:
        # First call: garbage. Second call: clean JSON. The second call must
        # succeed even though the first did not.
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(200, content="not json at all")
            return httpx.Response(200, content=json.dumps(_payload("ok", 0.9)))

        transport = httpx.MockTransport(handler)
        result = _make_ocr(transport).transcribe_image(str(small_image))
        assert result.ok is True
        assert result.transcription == "ok"
        assert call_count["n"] == 2

    def test_two_failures_raise_ocr_error(self, small_image: Path) -> None:
        transport = _StaticTransport(200, "plain text response, no JSON ever")
        with pytest.raises(OcrError):
            _make_ocr(transport).transcribe_image(str(small_image))


class TestHttpError:
    def test_5xx_raises_ocr_error(self, small_image: Path) -> None:
        transport = _StaticTransport(500, "boom")
        with pytest.raises(OcrError):
            _make_ocr(transport).transcribe_image(str(small_image))


class TestMissingFile:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        ocr = _make_ocr(_StaticTransport(200, "{}"))
        with pytest.raises(FileNotFoundError):
            ocr.transcribe_image(str(tmp_path / "missing.png"))


class TestPayload:
    def test_image_sent_as_base64(self, small_image: Path) -> None:
        body = json.dumps(_payload("x", 0.9))
        transport = _StaticTransport(200, body)
        _make_ocr(transport).transcribe_image(str(small_image))
        assert transport.last_request is not None
        import base64

        sent = json.loads(transport.last_request.content)
        assert sent["image_b64"] == base64.b64encode(small_image.read_bytes()).decode("ascii")
        assert "JSON" in sent["prompt"]


class TestCustomPrompt:
    """s18 — the optional ``prompt`` parameter is a backwards-compatible
    extension that lets :class:`app.services.ocr.evaluation_extractor
    .EvaluationExtractor` send a score-extraction prompt. The default
    behaviour (no ``prompt`` argument) must remain identical to the
    s10 contract — these tests lock that regression net.
    """

    def test_custom_prompt_is_sent_when_provided(self, small_image: Path) -> None:
        body = json.dumps(_payload("x", 0.9))
        transport = _StaticTransport(200, body)
        custom = "Renvoie UNIQUEMENT un JSON avec les clés score et max_score"
        _make_ocr(transport).transcribe_image(str(small_image), prompt=custom)
        assert transport.last_request is not None
        sent = json.loads(transport.last_request.content)
        assert sent["prompt"] == custom

    def test_no_prompt_means_default_behaviour_is_kept(
        self, small_image: Path
    ) -> None:
        """The default-prompt path must still produce a valid response
        (the s10 happy path). A regression that required ``prompt`` as
        a positional argument would break this test."""
        body = json.dumps(_payload("x", 0.9))
        result = _make_ocr(_StaticTransport(200, body)).transcribe_image(
            str(small_image)
        )
        assert result.ok is True
        assert result.transcription == "x"
