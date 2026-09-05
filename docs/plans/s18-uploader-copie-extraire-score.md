---
validated: yes
---
# Plan — Story s18-uploader-copie-extraire-score

Branch: `feature/s18-uploader-copie-extraire-score`
Research: `docs/research/s18-uploader-copie-extraire-score.md` — read it
first; this plan does not repeat it.

## Target story

**s18-uploader-copie-extraire-score** — As an élève I want to
téléverser une photo de ma copie d'évaluation corrigée par
l'enseignant so that le système extraie le score et les annotations.

**Complexity** : 4 (LLM vision + score extraction + edge cases). The
research confirmed a re-score of 3-4; we keep 4 for the OCR
non-determinism risk.

**Override of AC1** : the story says the body carries `pseudo`. s15
already retired that field (cf. `app/api/documents/router.py:131-156`
rejects `Form(pseudo)` with 422). The plan **overrides** this and the
router behaves the same way as the documents router: identity is
read from the JWT only, `Form(pseudo)` is rejected as a defense-in-
depth check. The override is documented in the research report and
recapped in the router's docstring; `docs/stories.md` is **not**
edited in this plan (drift documented, story update is a follow-up
housekeeping task — out of scope for s18).

## Tasks (ordered)

1. [x] **Add `Evaluation` model + `EvaluationStatus` enum in `models.py`**
   - New enum `EvaluationStatus` with values `SCORED` and
     `MANUAL_REVIEW_NEEDED` (s18b will reuse this enum; `ERROR` is
     not relevant — a copy is always persisted, even if the score
     is missing).
   - New ORM class `Evaluation` with columns: `id` (UUID PK),
     `student_pseudo` (FK `users.pseudo` CASCADE, indexed),
     `subject` (existing `Subject` enum), `s3_key` (String 512),
     `filename` (String 512), `status` (`EvaluationStatus`),
     `score` (Float, nullable), `max_score` (Float, nullable),
     `annotations` (JSON, nullable, list[str]),
     `teacher_comments` (String(8192), nullable), `ocr_text`
     (String(8192), nullable, the OCR transcript for auditability
     and reprocess in s18b), `ocr_confidence` (Float, nullable),
     `error_reason` (String(1024), nullable), `created_at` (DateTime
     server default now()).
   - No Alembic migration needed: `init_db()` applies the full
     `Base.metadata.create_all` in dev/CI (convention `models.py:166`,
     `Attempt` follows the same pattern).
   - **Test** : `tests/core/test_models.py` gains
     `test_evaluation_persists_with_minimum_fields` (insert + read
     roundtrip) and `test_evaluation_status_enum_has_two_values`
     (locks the enum surface for s18b).

2. [x] **Create `EvaluationExtractor` service in
   `app/services/ocr/evaluation_extractor.py`**
   - Class `EvaluationExtractor` taking a `MultimodalOcr` instance
     (constructor injection) and an `Settings` reference.
   - Constants `SCORE_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")` at
     module top (convention `text_grader.py:58` `VERDICT_RE`).
   - Dataclass `ExtractionResult(score: float | None,
     max_score: float | None, annotations: list[str],
     teacher_comments: str | None, ocr_text: str,
     ocr_confidence: float | None, source: Literal["regex",
     "llm", "none"])`.
   - Method `extract(image_path: str) -> ExtractionResult` :
     - Calls `self._ocr.transcribe_image(image_path, prompt=...)`
       using a **prompt custom** for score extraction
       (JSON strict : `{score, max_score, annotations,
       teacher_comments, ocr_text, ocr_confidence}`).
     - If the OCR call raises `OcrError` or returns `OcrResult.ok=
       False` (low confidence, empty text) → returns
       `ExtractionResult(source="none", ...)` and the caller maps
       to `MANUAL_REVIEW_NEEDED`.
     - On `ok=True`, runs `SCORE_RE.search(ocr_text)` first
       (fast path). If the regex finds a `<n>/<m>` pattern, the
       result carries `source="regex"`.
     - If the regex misses, parses the LLM JSON for `score` /
       `max_score` and carries `source="llm"`.
     - If both miss (no regex match AND LLM JSON `score` is null),
       `source="none"` → the caller maps to
       `MANUAL_REVIEW_NEEDED`.
   - **Refactor decision** : `MultimodalOcr.transcribe_image` does
     **not** accept a custom prompt today (`ocr.py:75`). We
     **extend** its signature with an optional `prompt: str | None
     = None` parameter (3-line change, 1 line in the test file
     updates, no behaviour change for s10 callers). This is
     cleaner than the duplication the research flagged. The
     implementer re-runs the existing `tests/services/rag/
     test_ocr.py` to confirm no regression.
   - **Test** (unit, in `tests/services/ocr/test_evaluation_extractor.py`,
     new file) :
     - `test_regex_picks_explicit_12_over_20` — mock OCR returns
       `"Note finale : 12/20. Très bien !"`, assert
       `source=="regex"`, `score==12.0`, `max_score==20.0`.
     - `test_llm_fallback_when_regex_misses` — mock OCR returns
       `ocr_text="très bien"` and the JSON wrapper carries
       `"score": 8, "max_score": 20` (no `/` in the text), assert
       `source=="llm"`, `score==8.0`.
     - `test_manual_review_when_neither_finds_score` — mock OCR
       returns `ocr_text="copie illisible"` and JSON
       `"score": null, "max_score": null`, assert
       `source=="none"`, `score is None`, `max_score is None`.
     - `test_ocr_low_confidence_short_circuits_to_none` — mock
       `OcrResult(ok=False, reason="low_confidence")`, assert
       `source=="none"` **without** the regex being attempted
       (verifies the short-circuit, Piège 5).
     - `test_ocr_error_raises_evaluation_extraction_error` — mock
       `transcribe_image` raises `OcrError`, assert the extractor
       raises `EvaluationExtractionError` (a new exception class
       so the router can map it to 500).

3. [x] **Create `EvaluationService` in the same file (orchestration)**
   - Class `EvaluationService` taking
     `(s3_client: MinioClient, extractor: EvaluationExtractor,
     session_factory: Callable, max_image_size_mb: int)`.
   - Constants `ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}`
     (images only — `documents` already accepts more, but s18
     specifies `file (image)` in AC1).
   - Exception `EvaluationError` with kind enum
     `EvaluationErrorKind { INVALID_FILE, STORAGE_FAILURE,
     EXTRACTION_FAILURE }` (mirror of `UploadError` /
     `UploadErrorKind`).
   - Method `upload(file_path: str, pseudo: str, subject: str) ->
     Evaluation` :
     - Validate extension (raises `INVALID_FILE` otherwise).
     - Validate size vs `max_image_size_mb` (raises `INVALID_FILE`).
     - Generate `evaluation_id = uuid.uuid4()`.
     - `s3_key = self._s3.put_object(pseudo=pseudo,
       document_id=evaluation_id, ...)` (raises
       `STORAGE_FAILURE` on `Exception`).
     - Call `self._extractor.extract(file_path)`. On
       `EvaluationExtractionError` (OCR unreachable), rollback
       the S3 object and raise `EXTRACTION_FAILURE`.
     - Compute final status : `SCORED` if
       `result.score is not None` else `MANUAL_REVIEW_NEEDED`.
     - Persist a single `Evaluation` row with all the extracted
       fields and the `s3_key`.
     - On any failure past the S3 push, **rollback the S3 object**
       (AC4 « persistance rien à moitié » — same contract as
       `upload_service.py:142-159`).
   - **Test** : `tests/services/ocr/test_evaluation_extractor.py`
     also covers the service in a second `TestEvaluationService`
     class :
     - `test_upload_persists_evaluation_row_with_score` — full
       happy path, score from regex, `Evaluation` row exists in
       SQLite.
     - `test_upload_persists_manual_review_when_no_score` — happy
       path with `source=="none"`, row exists with
       `status=MANUAL_REVIEW_NEEDED`, `score is None`.
     - `test_upload_rolls_back_s3_on_evaluation_persistence_error`
       — patch `session.add` to raise; assert
       `s3.remove_object` is called and no `Evaluation` row was
       committed.
     - `test_upload_rejects_pdf_extension` — `.pdf` file, expect
       `EvaluationError(INVALID_FILE)`.

4. [x] **Create Pydantic schemas in `app/api/evaluations/schemas.py`**
   - `UploadResponse` (mirror of `UploadResponse` documents) :
     fields `evaluation_id` (UUID), `status` (Literal["scored",
     "manual_review_needed"]), `score` (float | None),
     `max_score` (float | None), `annotations` (list[str]),
     `teacher_comments` (str | None), `ocr_confidence` (float |
     None). The `score`/`max_score` fields are `None` when the
     status is `manual_review_needed` (the frontend will display
     a banner — out of scope for s18).
   - `UploadErrorResponse` (mirror) : `error` + `code` Literal
     `["invalid_file", "extraction_failure", "storage_failure"]`.
   - Constants for the file-size guard match the documents router
     (no new setting in s18 — we re-use
     `settings.max_upload_size_mb` for consistency with `documents`).
   - **No Pydantic request model** : FastAPI binds the multipart
     fields directly via `Form()` / `File()` (same pattern as
     `documents/router.py:107-108`).

5. [x] **Create the factory in `app/api/evaluations/factory.py`**
   - `build_evaluation_service(settings: Settings) ->
     EvaluationService` (mirror of `documents/factory.py`).
   - `get_evaluation_service_dep()` for FastAPI dependency
     injection (returns a fresh instance per request — same
     YAGNI trade-off as the documents factory).
   - Wires the real `MinioClient`, a fresh `MultimodalOcr` (with
     `deepseek_ocr_url` and `deepseek_ocr_timeout` from settings),
     and `db_session.get_session_factory()`.
   - **No test in this task** : the factory is trivial wiring
     covered by the API integration tests; a unit test on a
     10-line builder is theatre.

6. [x] **Create the router `app/api/evaluations/router.py`**
   - `APIRouter(prefix="/api/evaluations", tags=["evaluations"])`.
   - Endpoint `POST /upload` (single endpoint for s18; s18b adds
     `/{id}/score-manual` and `/{id}/reprocess`).
   - `Depends(get_current_user)` for the JWT. RBAC: **no
     `require_role` filter** — the documents upload is open to
     `eleve` + `parent` + `admin` (cf. RBAC matrix in
     `CLAUDE.md` § Permissions RBAC : `✅ (tous)` for upload). A
     `parent` may upload on behalf of a linked child — but the
     story is silent on this. **Decision** : s18 only lets the
     **JWT user** upload, with `student_pseudo = user.pseudo`.
     Parents uploading for their children are out of scope (the
     dashboard parent story s17 already pulls children's data;
     s18b can add a "submit on behalf of" mode if requested).
     Override documented in the docstring.
   - `assert_jwt_pseudo_matches_or_403(user, claimed=None, ...)`
     defensive no-op (mirrors `documents/router.py:129`).
   - `subject: Literal["maths", "francais"] = Form(...)`,
     `file: UploadFile = File(...)`. **No `Form(pseudo)`** —
     hard cut per s15.
   - Drift defense : parse `await request.form()` and reject any
     field outside `{subject, file}` with 422
     `value_error.extra` (same code as
     `documents/router.py:138-155`).
   - Triple size guard (Content-Length → post-read → service),
     same code as `documents/router.py:157-184` (copy verbatim,
     then refactor in a follow-up if needed — out of scope).
   - Materialize the upload to a `tempfile.NamedTemporaryFile`
     with the original suffix (the OCR client inspects the
     suffix), `finally` cleanup identical to
     `documents/router.py:193-242`.
   - Call `service.upload(tmp_path, user.pseudo, subject)`.
   - Map `EvaluationError` to HTTP status codes :
     `INVALID_FILE` (extension) → 415, `INVALID_FILE` (size) →
     413, `EXTRACTION_FAILURE` → 422, `STORAGE_FAILURE` → 500.
     Discrimination by substring on the service message (same
     trick as `documents/router.py:78-90`).
   - **Tests** (`tests/api/test_evaluations.py`, new file) :
     - `test_upload_persists_evaluation_with_score` (AC1+AC2+
       AC5+AC6 happy path) — POST a tiny PNG, mock the OCR
       transport to return `"Note : 12/20"`, assert 201 with
       `status="scored"`, `score==12.0`, `max_score==20.0`,
       and the DB has a row.
     - `test_upload_persists_manual_review_when_no_score` (AC4+
       AC7) — POST a PNG, mock OCR returns `ocr_text="copie
       illisible"` and JSON `"score": null`, assert 201 with
       `status="manual_review_needed"`, `score is None`.
     - `test_upload_returns_415_for_pdf_extension` — POST a
       `.pdf`, assert 415 and `code="invalid_file"`.
     - `test_upload_returns_413_when_content_length_exceeds_max`
       — POST with a Content-Length header over the cap, assert
       413 without reading the body (Level 1 guard).
     - `test_upload_returns_413_when_body_exceeds_max` — POST a
       body that exceeds the cap, assert 413 (Level 2 guard).
     - `test_upload_rejects_form_pseudo_field` (drift s15) — POST
       with an extra `pseudo=other_user` field, assert 422
       `value_error.extra` and no row created.
     - `test_upload_returns_401_without_jwt` (RBAC) — POST
       without `Authorization`, assert 401 `invalid_token`.
     - `test_upload_uses_jwt_pseudo_not_form` (AC8 cross-tenant
       bite) — login as `alice`, POST with `pseudo=bob` in the
       form, assert 422 (the field is rejected) and no row for
       `bob` is created.
     - `test_upload_rolls_back_s3_on_persistence_error` — patch
       the session to fail on commit, assert 500 and the S3
       object is removed.
     - `test_upload_returns_500_on_storage_failure` — patch the
       `MinioClient.put_object` to raise, assert 500.
     - `test_upload_returns_422_on_ocr_unreachable` — mock
       `transcribe_image` to raise `OcrError`, assert 422
       `extraction_failure`.

7. [x] **Mount the router in `app/main.py`**
   - Import `from app.api.evaluations.router import router as
     evaluations_router` next to the other imports
     (`app/main.py:27-32`).
   - Add `app.include_router(evaluations_router)` next to the
     other `include_router` calls
     (`app/main.py:75-80`).
   - **No test in this task** : the existing smoke test (smoke
     import) is the regression net; a dedicated test for an
     `include_router` line is theatre.

8. [x] **Add the cross-tenant isolation bite (AC8)**
   - The `student_pseudo` column is a FK to `users.pseudo`
     CASCADE, so direct cross-tenant access via the ORM is
     impossible. The test in Tâche 6
     (`test_upload_uses_jwt_pseudo_not_form`) is the
     cross-tenant bite for the **upload** path. The read path
     (GET /api/evaluations/{id}) is **out of scope** for s18
     (s18b will add the manual-score + reprocess endpoints; a
     GET is not on the s18 or s18b perimeter per
     `docs/stories.md`).
   - Verify the SQL `Evaluation` row is **always** keyed by
     `user.pseudo` (from JWT), never from the form body — this
     is asserted by `test_upload_uses_jwt_pseudo_not_form`
     already.
   - **No new test in this task** : the test is the Tâche 6
     bite, retitled here to make the AC8 trace explicit.

9. [x] **Update `docs/stories.md` is OUT OF SCOPE**
   - The story's AC1 mentions `pseudo` in the body — this
     plan overrides it. We **do not** edit `docs/stories.md`
     (the drift is documented in the research report). If a
     follow-up story update is desired, file a small chore
     later. The plan stays focused on the implementation.

10. [x] **Create the two ADRs (research § Décisions architecturales)**
    - **ADR 012 — evaluation-ocr-via-multimodal-llm-with-
      custom-prompt** : status `accepted`, scope `story s18`.
      Records the decision to extend
      `MultimodalOcr.transcribe_image` with an optional
      `prompt` parameter (vs duplicating the transport in
      `EvaluationExtractor`). Rejected alternatives :
      duplication, separate OCR chain.
    - **ADR 013 — evaluation-status-enum-dedie** : status
      `accepted`, scope `story s18`. Records the decision to
      introduce `EvaluationStatus {SCORED, MANUAL_REVIEW_NEEDED}`
      instead of reusing `DocumentStatus` (the meanings
      diverge: a document is `error` when ingestion failed;
      an evaluation is **always** persisted, the status only
      reflects the score extraction). Rejected alternative :
      reuse `DocumentStatus`.
    - Both ADRs follow `@templates/adr.md` (Context / Decision /
      Considered options / Consequences).
    - **No test** : ADRs are documentation.

11. [x] **One commit at the end of the story**
    - The implementer writes the whole story in a single
      commit carrying the docs (research, plan, ADRs) and all
      the code (model, service, router, factory, schemas,
      tests). This is the AGENTS.md § Git et PR convention.

## Run interdicts

- **Do not create the feature branch in the repository base
  directory.** Stay in
  `C:\Workspace\ktutor\.worktrees\s18-uploader-copie-extraire-score`
  (verified : `feature/s18-uploader-copie-extraire-score`,
  HEAD 46ad4bc, clean apart from `.env.bak*` which are
  gitignored and the new research file).
- **Do not modify `MultimodalOcr`'s public contract beyond the
  optional `prompt` parameter.** The existing callers in
  `services/rag/upload_service.py` must keep working — re-run
  `tests/services/rag/test_ocr.py` to confirm.
- **Do not add a new setting to `app/core/config.py`** unless
  a task explicitly requires it. The image size reuses
  `settings.max_upload_size_mb`; new constants live in the
  service module.
- **Do not create a rewards service** in s18 (the
  gamification for evaluation upload is out of scope — CLAUDE.md
  mentions 10 points, but `services/rewards/` does not exist
  and a future story will own that pattern).
- **Do not edit `docs/stories.md`** in this story. The AC1
  drift is documented in the research; updating the story
  file is a follow-up.
- **Do not introduce a Celery task for OCR.** The upload is
  synchronous (ADR 010 only covers the chat streaming; no
  background processing for evaluations). The latency budget
  is the OCR call (50-200 ms locally per ADR 008).
- **Do not add a GET endpoint.** The story is upload-only.
  The dashboard surfaces the data (out of scope, s20+).
- **Do not log the OCR text, the extracted score, or the
  filename in a way that leaks the student's identity beyond
  `pseudo` (AGENTS.md § Logs).** Use `loguru` structured JSON
  with fields `pseudo`, `route`, `duration_ms`, `status`,
  `score_present` (bool). Never log `teacher_comments` or
  `annotations` content.

## The point everything turns on

The plan stands on **the dual-source extraction contract** :
the regex is a fast path on the OCR text, the LLM is the
fallback when the regex misses. Three places this could
break :

1. **DeepSeek-OCR-2's prompt for the structured JSON** is
   brittle (it may return a JSON that doesn't match our
   schema). The `EvaluationExtractor` must use a strict
   prompt (mirroring `_build_strict_prompt` in
   `ocr.py:116-120`) and a tolerant parser. **Compare
   against** : the existing `MultimodalOcr` retry-once-with-
   strict-prompt behaviour (`ocr.py:85-93`). We can reuse
   the same `_try_parse_json` helper (refactor it out of
   `ocr.py` if duplication grows).
2. **The regex anchoring** matters. The agentic notes
   flagged the false-positive risk (« élève noté 12 sur
   20 »). The plan keeps the regex narrowly anchored on
   `\b(\d+)\s*/\s*(\d+)\b` and uses the LLM only when the
   regex misses. **Compare against** : the LLM-only
   approach (one call, no regex) — more robust against
   weird score formats but more expensive and slower. The
   regex is cheap insurance.
3. **`MANUAL_REVIEW_NEEDED` is a successful HTTP outcome,
   not an error.** The router returns 201 with the
   `status` field carrying the flag — same convention as
   `documents` (`router.py:222-224`). The frontend
   (out of scope) will branch on the field. **Compare
   against** : returning 422 ("score not extracted") —
   semantically wrong because the upload IS persisted.

## Files touched

**Created** :
- `backend/app/services/ocr/__init__.py`
- `backend/app/services/ocr/evaluation_extractor.py`
- `backend/app/api/evaluations/__init__.py`
- `backend/app/api/evaluations/router.py`
- `backend/app/api/evaluations/schemas.py`
- `backend/app/api/evaluations/factory.py`
- `backend/tests/services/ocr/__init__.py`
- `backend/tests/services/ocr/test_evaluation_extractor.py`
- `backend/tests/api/test_evaluations.py`
- `docs/decisions/012-evaluation-ocr-via-multimodal-llm-with-custom-prompt.md`
- `docs/decisions/013-evaluation-status-enum-dedie.md`

**Modified** :
- `backend/app/core/database/models.py` (add `Evaluation` +
  `EvaluationStatus`)
- `backend/app/services/rag/ocr.py` (extend
  `transcribe_image` with optional `prompt: str | None`)
- `backend/app/main.py` (include the new router)
- `backend/tests/core/test_models.py` (extend with the
  `Evaluation` roundtrip and enum-locking tests)
- `backend/tests/services/rag/test_ocr.py` (regression net
  on the `prompt=None` default)

**Not modified** :
- `docs/stories.md` (drift documented, not edited)
- `backend/app/core/config.py` (no new setting)
- any frontend file (no UI in s18)

## Test strategy

The 11 tests in Tâches 1-6 + 8 cover the 8 ACs plus the
defense-in-depth bites. Layered as follows :

- **Unit (service)** : Tâche 2 (5 tests) +
  Tâche 3 (4 tests) — `tests/services/ocr/
  test_evaluation_extractor.py`. Pure business logic,
  mocked OCR transport.
- **Model** : Tâche 1 (2 tests) — `tests/core/test_models.py`.
  ORM roundtrip + enum surface.
- **Regression net on `MultimodalOcr`** : Tâche 2
  (1 test) — `tests/services/rag/test_ocr.py` confirms the
  optional `prompt` parameter defaults to the existing
  behaviour.
- **Integration (API)** : Tâche 6 (11 tests) — `tests/api/
  test_evaluations.py`. Multipart, RBAC, size guards,
  drift defense, cross-tenant bite, S3 rollback, OCR
  failure paths.

Total : **22 tests**, all hermetic (SQLite in-memory +
`httpx.MockTransport`, no live services).

No visual verification needed (no UI).

## Definition of Done

- All 11 plan tasks checked.
- 22 tests pass (`pytest backend/tests`).
- `tests/services/rag/test_ocr.py` still passes (the
  `prompt` extension is backwards-compatible).
- `git diff main...feature/s18-uploader-copie-extraire-score`
  shows a clean diff scoped to the files listed above.
- One single commit at the end of the story.
- The two ADRs (012, 013) are committed on the feature
  branch (not on `main`).
- The review (`/ks-review s18`) ends with
  `Ship allowed: yes`.

## Complexity verification

Story complexity is 4, plan has 11 tasks. AGENTS.md says a
plan that grows past ~10 tasks is a sign the story is too
big. The plan is at the limit. Justification for not
splitting :
- Tasks 1, 9, 10, 11 are documentation / bookkeeping
  (model, override, ADRs, commit) — they don't add
  implementation surface.
- Tasks 2 + 3 are tightly coupled (the service is a thin
  wrapper over the extractor) — splitting them would
  force a fictional boundary.
- Task 6 (router) is the largest single unit, but it's a
  single endpoint with one test family per AC. Splitting
  the router would create false granularity.

If the implementer feels the plan bloats at execution time,
the natural split is **Tâche 6** (router) out of **Tâches
2-3** (service) by doing the service first in a separate
PR. But this is a YAGNI split for a 4-complexity story.
