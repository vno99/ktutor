"""Tests for ``POST /api/chat/stream`` (s09).

The suite covers every acceptance criterion in the story plus the
cross-tenant bite required by the repo Definition of Done (AGENTS.md):

* AC1 — JSON body, ``text/event-stream`` content type.
* AC2 — Each event carries one token chunk.
* AC3 — Final event is ``{done: True, sources: [...]}``.
* AC4 — Agent error becomes an ``{error, code}`` event and the
  connection closes.
* AC5 — CORS preflight works for the allow-listed origin and is
  refused for any other.
* AC6 — Tokens arrive in order.
* AC7 — A request with missing fields returns 422 BEFORE any stream
  is opened.

The cross-tenant bite is :func:`test_cross_tenant_via_body_swap` — it
posts ``pseudo="bob"`` to a supervisor whose maths agent raises
``ValueError("different pseudo")`` for any non-``"alice"`` request, and
asserts the response carries ``code: "cross_tenant"``.
"""

from __future__ import annotations

import json
import re

import pytest


def _events_from_response(response) -> list[dict]:
    """Parse an SSE response body into a list of payload dicts."""
    events: list[dict] = []
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# AC7 — request validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_missing_question_returns_422(self, client) -> None:
        """Bite test: Pydantic validates BEFORE the handler runs, so a
        body without ``question`` yields 422 and no stream is opened.
        """
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths"},
        )
        assert response.status_code == 422
        # The error payload must mention the missing field.
        body = response.json()
        assert any(
            err.get("loc", [])[-1] == "question" for err in body.get("detail", [])
        )

    def test_missing_pseudo_returns_422(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
        )
        assert response.status_code == 422

    def test_invalid_pseudo_format_returns_422(self, client) -> None:
        """The pseudo regex rejects spaces, accents, and other non
        ``[a-zA-Z0-9_]`` characters.
        """
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "ali ce", "subject": "maths", "question": "2+2 ?"},
        )
        assert response.status_code == 422

    def test_unknown_subject_returns_422(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "histoire", "question": "Q"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC1, AC2, AC3, AC6 — happy path
# ---------------------------------------------------------------------------


class TestStreamHappyPath:
    def test_stream_returns_text_event_stream(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "2+2 ?"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    def test_stream_emits_one_event_per_token(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "2+2 ?"},
        )
        events = _events_from_response(response)
        # 3 tokens + 1 done event.
        assert [e for e in events if "token" in e] == [
            {"token": "Hel"},
            {"token": "lo "},
            {"token": "world"},
        ]

    def test_stream_ends_with_done_event(self, client, maths_stub) -> None:
        from app.services.agents.types import SourceCitation

        maths_stub.sources = [SourceCitation(filename="cours.pdf", chunk_index=0)]
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "2+2 ?"},
        )
        events = _events_from_response(response)
        # The last event must be ``done: True`` with the sources list.
        assert events[-1] == {
            "done": True,
            "sources": [{"filename": "cours.pdf", "chunk_index": 0}],
        }

    def test_stream_chunks_arrive_in_order(self, client) -> None:
        """Bite test: the chunks must arrive in the order the supervisor
        yielded them. A bug that re-ordered or re-grouped them would
        silently scramble the response text in the browser.
        """
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "francais", "question": "métaphore ?"},
        )
        events = _events_from_response(response)
        token_events = [e for e in events if "token" in e]
        assert [e["token"] for e in token_events] == ["Une ", "métaphore."]


# ---------------------------------------------------------------------------
# AC4 — error events
# ---------------------------------------------------------------------------


class TestStreamError:
    def test_error_event_emitted_with_code(self, client, maths_stub) -> None:
        """Bite test: a ``ValueError`` from the agent must be caught and
        forwarded as an ``{error, code}`` event. The ``code`` is mapped
        from the error message (``"subject"`` substring → ``no_subject``).
        """
        maths_stub.behaviour = "raise_subject"
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "Q"},
        )
        # The HTTP status stays 200 — the error is in the SSE body. The
        # connection closes cleanly after the error event.
        assert response.status_code == 200
        events = _events_from_response(response)
        # The error event must be present with the right code.
        assert any(
            e.get("code") == "no_subject" and "Unknown subject" in e.get("error", "")
            for e in events
        )
        # No ``done`` event after an error.
        assert not any("done" in e for e in events)

    def test_cross_tenant_via_body_swap(self, client, maths_stub) -> None:
        """Bite test: a request whose ``pseudo`` is NOT the one the agent
        is willing to serve must yield a ``cross_tenant`` code in the
        error event. The router MUST pass ``body.pseudo`` to the
        supervisor unchanged — a regression that hardcoded ``"alice"``
        in the router would not be caught by any other test.
        """
        maths_stub.behaviour = "raise_cross_tenant"
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "bob", "subject": "maths", "question": "Q"},
        )
        events = _events_from_response(response)
        # The supervisor was called with the body's pseudo, not a
        # hardcoded value. The agent's guard raised, the router caught
        # it, and ``_map_code`` matched the "different" substring.
        assert any(
            e.get("code") == "cross_tenant" and "different" in e.get("error", "")
            for e in events
        )
        # The supervisor MUST have been called with the body pseudo.
        assert maths_stub.astream_calls[-1][1] == "bob"

    def test_unknown_error_maps_to_unknown_code(self, client, maths_stub) -> None:
        maths_stub.behaviour = "raise_unknown"
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "Q"},
        )
        events = _events_from_response(response)
        assert any(e.get("code") == "unknown" for e in events)


# ---------------------------------------------------------------------------
# SSE format
# ---------------------------------------------------------------------------


class TestSseFormat:
    def test_each_event_ends_with_double_newline(self, client) -> None:
        """Bite test: each SSE event MUST end with ``\\n\\n`` so the
        browser fires ``onmessage``. Removing the trailing newline
        from :func:`format_sse` would break every frontend consumer.
        """
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "Q"},
        )
        # ``iter_lines`` preserves the wire format including the blank
        # line that separates events.
        lines = list(response.iter_lines())
        # The body alternates ``data: ...`` and ``""`` (the blank
        # separator). There must be no ``data: ...`` line followed by
        # a non-empty line — every event must be self-contained.
        for i, line in enumerate(lines):
            if line.startswith("data: ") and i + 1 < len(lines) and lines[i + 1] != "":
                # If we ever see ``data: foo`` immediately followed
                # by ``data: bar`` without a blank line, the test
                # fails. The current TestClient may merge lines,
                # so we instead assert the raw text format.
                pytest.fail(
                    f"Event at line {i} not followed by a blank separator: {lines[i:i+3]!r}"
                )
        # The body text itself must match the canonical
        # ``data: <json>\n\n`` regex on every event block.
        blocks = re.findall(r"data: [^\n]+\n\n", response.text)
        assert blocks, f"No SSE blocks found in body: {response.text!r}"
        for block in blocks:
            assert re.match(r"^data: \{.*\}\n\n$", block), (
                f"Block does not match canonical SSE format: {block!r}"
            )

    def test_preserves_non_ascii_characters(self, client) -> None:
        """Bite test: ``ensure_ascii=False`` keeps French characters
        intact in the wire bytes. The frontend's ``new TextDecoder``
        does not have to handle ``\\u00xx`` escapes.
        """
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "francais", "question": "Q"},
        )
        # The French token ``métaphore`` must appear verbatim.
        assert "métaphore" in response.text


# ---------------------------------------------------------------------------
# AC5 — CORS
# ---------------------------------------------------------------------------


class TestCors:
    def test_cors_preflight_allowed_for_allowlisted_origin(self, client) -> None:
        response = client.options(
            "/api/chat/stream",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code in (200, 204)
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )

    def test_cors_preflight_rejected_for_other_origin(self, client) -> None:
        """Bite test: an origin NOT in the allow-list must NOT receive
        the CORS allow headers. Using ``allow_origins=["*"]`` would
        weaken the test to a no-op.
        """
        response = client.options(
            "/api/chat/stream",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # Starlette's CORS middleware refuses the preflight with 400.
        assert response.status_code == 400
        assert "access-control-allow-origin" not in {
            k.lower() for k in response.headers
        }

    def test_actual_post_includes_allow_origin_header(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "Q"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )


# ---------------------------------------------------------------------------
# Chat stream safety net
# ---------------------------------------------------------------------------


class TestSafetyNet:
    def test_max_chunks_safety_net_stops_runaway_stream(
        self, maths_stub, supervisor_stub
    ) -> None:
        """Bite test: the ``chat_stream_max_chunks`` setting caps the
        stream. A bug that ignored the cap would let a runaway LLM
        flood the SSE channel.
        """
        from fastapi.testclient import TestClient

        from app.api.chat.router import _build_supervisor_dep
        from app.core.config import Settings
        from app.main import app

        # Many tokens -> exceeds the cap.
        maths_stub.tokens = [f"t{i}" for i in range(20)]
        tiny = Settings(chat_stream_max_chunks=5, cors_allow_origins="http://localhost:3000")

        app.dependency_overrides[_build_supervisor_dep] = lambda: supervisor_stub
        # Override the get_settings dependency to return the tiny cap.
        from app.core import config as config_module

        original_get_settings = config_module.get_settings
        config_module._settings = tiny  # populate the cache directly
        try:
            with TestClient(app) as c:
                response = c.post(
                    "/api/chat/stream",
                    json={"pseudo": "alice", "subject": "maths", "question": "Q"},
                )
            events = _events_from_response(response)
            token_events = [e for e in events if "token" in e]
            assert len(token_events) <= 5
            assert any(
                e.get("code") == "unknown" and "safety net" in e.get("error", "")
                for e in events
            )
        finally:
            config_module._settings = None
            config_module.get_settings = original_get_settings
            app.dependency_overrides.pop(_build_supervisor_dep, None)
