"""OCR-domain services.

s18 — the :class:`EvaluationExtractor` and :class:`EvaluationService`
classes live here. They sit on top of :mod:`app.services.rag.ocr`'s
:class:`MultimodalOcr` (the s01 vision LLM client) but speak a
different language: where ``MultimodalOcr`` returns a generic
:class:`OcrResult`, ``EvaluationExtractor`` returns a structured
:class:`ExtractionResult` with a clear ``source`` discriminator
(``regex`` / ``llm`` / ``none``). The contract is recorded in
ADR 012.
"""
