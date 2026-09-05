# ADR 012 — Score extraction via multimodal LLM with a custom prompt

- Status: accepted
- Date: 2026-09-05
- Scope: story s18

## Context

The evaluation copy upload (s18) must extract a score, max_score,
annotations, teacher_comments and OCR text from a single image of a
corrected exam. The image is a mix of typed text, handwritten
answers, and teacher annotations. The story AC3 says "use a regex
for explicit scores like 12/20 AND an LLM call for unstructured
comments".

The current OCR client (`MultimodalOcr`,
`app/services/rag/ocr.py`) speaks to the local DeepSeek-OCR-2 service
(ADR 008). It accepts a hard-coded prompt that asks for
``{transcription, type, confidence, has_math}`` — the right shape for
document indexing (s10) but the wrong shape for score extraction.

Two implementation paths were on the table:

1. **Extend `MultimodalOcr.transcribe_image` with an optional
   ``prompt`` parameter.** The default behaviour stays identical
   (the s10 contract is preserved), the new code path lets
   `EvaluationExtractor` ask the LLM for
   ``{score, max_score, annotations, teacher_comments, ocr_text,
   ocr_confidence}``. The full LLM JSON envelope is preserved in a
   new optional ``raw`` field on :class:`OcrResult` so callers that
   need the structured fields (e.g. ``score``) do not have to
   re-parse the response.
2. **Create a parallel `EvaluationOcr` client that owns its own
   transport.** Strict isolation from s10, no risk of regression on
   the documents pipeline, but ~80 lines of duplicated HTTP
   plumbing (retry, JSON fence stripping, confidence gate) that
   would have to be kept in lock-step with `MultimodalOcr`.

## Decision

Adopt option 1 — extend `MultimodalOcr` with the optional ``prompt``
parameter and the optional ``raw`` field on `OcrResult`. The
`EvaluationExtractor` (s18) and the documents `UploadService` (s10)
share the same HTTP client and the same retry / parsing machinery.

The new fields are both optional (``prompt: str | None = None`` on
the call, ``raw: dict | None = None`` on the result). Existing
s10 callers see no API change; the existing
`tests/services/rag/test_ocr.py` suite continues to pass
(12 tests as of s18, including two new ones that lock the
backwards-compat behaviour).

## Considered options

- **Option 1 — extend `MultimodalOcr` (chosen)** : one transport,
  two prompts, no duplication. The cost is one new optional
  parameter on a public method and one new optional field on a
  public dataclass — both backwards-compatible.
- **Option 2 — duplicate the transport in `EvaluationExtractor`** :
  strict isolation, no risk to s10, but ~80 lines of duplicated
  logic (retry, JSON fence stripping, confidence gate). The
  research rejected this in Drift 2: "the plan should avoid
  duplication that has to be kept in lock-step".
- **Option 3 — call the LLM twice (OCR pass + score-extraction
  pass)** : strictly modular, but doubles the latency (~50-200 ms
  per call per ADR 008) and gives the OCR a worse view of the
  document because the second call sees the OCR's text, not the
  image. Rejected on cost.

## Consequences

- **Easier** : a new structured-extraction caller can plug in
  without writing a new HTTP client.
- **Easier** : the regex fast path in `EvaluationExtractor` runs on
  the LLM's natural-language ``transcription`` (the
  ``ocr_text`` field the LLM already returned), no extra HTTP call.
- **Harder** : the public surface of `MultimodalOcr` grows by two
  optional fields. The contract is documented in the docstring of
  `transcribe_image` and `OcrResult`; future refactors must keep
  these backwards-compatible.
- **Watch** : the LLM prompt is in French and instructs the model
  to return ``null`` rather than guess a score. A regression that
  drops the "no devine pas" clause would let the LLM hallucinate
  scores — the test
  `test_llm_fallback_when_regex_misses` and the prompt-capture
  test `test_custom_prompt_is_sent` lock the contract.
- **Watch** : the `raw` field exposes the full LLM envelope to any
  caller. Future callers must not write to it; the field is
  intended as a read-only view of what the LLM sent back.
