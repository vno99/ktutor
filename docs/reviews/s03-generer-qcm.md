# Review — s03-generer-qcm

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-08-29
> Source : `git diff main...feature/s03-generer-qcm` vs `docs/plans/s03-generer-qcm.md` + `docs/research/s03-generer-qcm.md` + ADRs 001/002/003/004/005/006/008/009.
> Tests : **161 passés** (lancés par le reviewer) — couverture **86,60%** (seuil 80%). `qcm_generator.py` 88%, `retriever.py` 100%.
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s03-generer-qcm` (branche `feature/s03-generer-qcm`).

## Test suite + lint

- Ran `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"` myself: 161 passed, coverage 86.60% (well above 80%). `qcm_generator.py` covered at 88%, `retriever.py` at 100%.
- Ran `cd backend && ruff check app tests` myself: all checks passed.

## Diff vs plan, task by task

| Plan task | Status |
| --- | --- |
| Étape 0.1 — config QCM (4 settings) | Done. `qcm_default_questions=5`, `qcm_max_questions=20`, `qcm_max_retries=1`, `qcm_temperature=0.0`. Verified. |
| Étape 0.2 — `.env.example` | Done. 4 vars added. |
| Étape 0.3 — `Exercise` + `ExerciseType` | Done. `ExerciseType.QCM` enum, `Exercise` with `student_pseudo`, `subject`, `type`, `document_id`, `statement/expected_answer/grading_criteria` (all nullable), `questions` (JSON), `created_at`. Uses `sqlalchemy.JSON` (not `JSONB`). |
| Étape 0.4 — `Retriever.get_chunks_for_document` | Done. Validates UUID, calls `chroma.get_collection(subject, pseudo)`, filters by `where={"document_id": document_id}`. Multi-tenant invariant preserved (collection name not exposed). |
| Étape 1.5 — `QcmGenerator` | Done. Pydantic schemas (`QcmQuestion` with `Field(ge=0, le=3)` and `min_length=4, max_length=4`), retry with strict prompt, ownership check, persistence. |
| Étape 2.6 — CLI `generate-qcm` | Done. `_build_qcm_service`, exit codes mapped. |
| Étape 3.7 — `docs/architecture.md` update | Done. Schema for `exercises` updated. |
| Étape 4.8/9/10 | Tests pass, ruff clean, manual verification deferred to human. |

**No drift** — the diff stays inside the plan's scope. Run interdicts respected:
- `services/llm/client.py` (s02) untouched.
- `services/agents/maths_agent.py` (s02) untouched.
- `services/rag/chroma_store.py` (s01) untouched.
- `services/rag/upload_service.py` (s01) untouched.
- `MinioClient` and `ChromaStore` names preserved.
- `sqlalchemy.JSON` used (not `JSONB`).
- No new LLM provider wired.
- No Alembic migration created.

## Acceptance criteria verification

| AC | Test | Result |
| --- | --- | --- |
| AC1 (CLI returns n questions, 4 options, correct_index 0-3) | `test_cli.py::TestGenerateQcm::test_generate_qcm_returns_zero_with_n_questions` + `test_generate_qcm_json_output_is_valid` + `test_qcm_generator.py::TestSchema::test_qcm_question_schema_validates_4_options_and_correct_index_range` | Verified. |
| AC2 (valid JSON, parsable) | `TestGenerateHappyPath::test_generate_returns_valid_json` | Verified (round-trip through `json.loads`). |
| AC3 (filtered by `document_id`) | `TestDocumentFilter::test_generate_filters_chunks_by_document_id` + `TestGetChunksForDocument::test_get_chunks_for_document_returns_only_target_document` | Verified — `TARGET_CONTENT` is in the prompt, `OTHER_CONTENT` is not. |
| AC4 (retry on malformed output, then clear error) | `TestRetry::test_generate_retries_once_on_malformed_output` + `test_generate_fails_after_max_retries` | Verified — first attempt + 1 retry, then `malformed_output` error. |
| AC5 (persistence with metadata) | `TestPersistence::test_generate_persists_exercise_in_session` + `test_generate_raises_document_not_found_for_unknown_uuid` + `test_generate_raises_document_not_found_for_cross_tenant` | Verified — `session.add(Exercise(...))` is observed; metadata fields populated. |
| AC6 (schema: 4 options, 1 correct_index in [0,3]) | `TestSchema::test_qcm_question_schema_validates_4_options_and_correct_index_range` + `test_qcm_question_rejects_wrong_options_count` + `test_qcm_question_rejects_out_of_range_correct_index` | Verified. |

## Multi-tenancy invariant

- `Retriever.get_chunks_for_document` accepts `(subject, pseudo, document_id)` — never a collection name. The collection is always obtained via `chroma.get_collection(subject, pseudo)`. ADR 004 honored.
- `QcmGenerator.generate` calls `session.get(Document, doc_uuid)` and checks `doc.student_pseudo == pseudo`. Cross-tenant requests raise `document_not_found` with the same message as missing-document (no leak).
- `Retriever` validates the pseudo via `validate_pseudo` before reaching ChromaDB.

## Retry logic

- `attempts = self._max_retries + 1` (1 first attempt + 1 retry when `max_retries=1`). Confirmed.
- First attempt uses soft prompt; retry uses strict prompt (`_STRICT_USER_PROMPT_TEMPLATE`). Confirmed.
- `test_generate_fails_after_max_retries` proves exactly 2 LLM calls on `["not json", "still not json"]`.

## Pydantic schema

- `QcmQuestion.options: list[str] = Field(min_length=4, max_length=4)` enforced.
- `QcmQuestion.correct_index: int = Field(ge=0, le=3)` enforced.
- `QcmExercise.questions: list[QcmQuestion] = Field(min_length=1)` enforced.
- Pydantic 2.13.4 str→int coercion verified live: `model_validate({"correct_index": "2"})` produces int 2.

## Persistence

- `session.add(Exercise(id=..., student_pseudo=pseudo, subject=Subject(subject), type=ExerciseType.QCM, document_id=doc_uuid, questions=[q.model_dump() for q in qcm.questions]))` followed by `session.commit()`. Wrapped in try/except with rollback. Verified in tests via `_TrackingSession` wrapper.

## Mutation testing (bites I neutralized)

I copied the backend to `/tmp/mutation_test_project` and applied four mutations, then restored:

1. **Removed `doc.student_pseudo != pseudo` ownership check** → `test_generate_raises_document_not_found_for_cross_tenant` turned RED (1 red). Test correctly bites.
2. **Removed `where={"document_id": document_id}` filter in `Retriever.get_chunks_for_document`** → `test_generate_filters_chunks_by_document_id` AND `test_get_chunks_for_document_returns_only_target_document` turned RED (2 red). Test correctly bites.
3. **Removed `session.add(Exercise(...))`** → `test_generate_persists_exercise_in_session` turned RED (1 red). Test correctly bites.
4. **Set `attempts = 1` (no retry)** → `test_generate_retries_once_on_malformed_output` AND `test_generate_fails_after_max_retries` turned RED (2 red). Test correctly bites.

All four central invariants are test-protected. The cross-tenant test even asserts `llm.calls == []` — the LLM is never invoked on a cross-tenant request, which is the strongest possible test of the multi-tenant lock.

After each mutation, I reverted and re-ran the full suite. Final state: worktree is clean (`git status` = "nothing to commit, working tree clean").

## Test quality

The tests are not decorative. They:
- Use real ChromaDB (`chromadb.EphemeralClient`) to verify the `where` filter actually applies.
- Use real SQLite in-memory to verify the model persists and the generator's `session.add` is called.
- Use a custom `_TrackingSession` wrapper specifically to detect `session.add` calls that would otherwise be invisible after `session.commit()` (a thoughtful, deliberate design).
- Script the LLM via `_ScriptedLlm` returning predefined responses — the LLM is not a mock on the response surface but a deterministic oracle.
- Cross-tenant test goes beyond "wrong kind" — it also asserts `llm.calls == []` (no LLM invocation at all).
- No assertions on CSS classes, prop echoes, or DOM (backend story).

## Findings

#### critical
None.

#### major
None.

#### minor

1. **No test for Pydantic str→int coercion on `correct_index`.** The research explicitly flagged this as a Pydantic 2 "neutralized trap" (LLM may output `"2"` as a string) and the plan says "le test doit verrouiller le comportement" — but no test asserts that `QcmQuestion.model_validate({"correct_index": "2", ...})` produces an int. I verified live that Pydantic 2.13.4 does coerce, so the behavior is correct; only the test is missing. This is a coverage gap, not a defect.

2. **Plan and research files committed on the feature branch.** `docs/plans/s03-generer-qcm.md` and `docs/research/s03-generer-qcm.md` are added in the s03 commit (`71d7f45`), inflating the diff to +464 lines that are review inputs rather than feature code. The s02 commit followed the same pattern, so this is consistent with project convention — but it does make `git diff main...feature/s03-generer-qcm` larger than necessary.

3. **Minor coverage gap in `qcm_generator.py` (88%).** Lines not covered: the `except Exception: session.rollback(); raise` block (line 333-335) and the `if not chunks:` branch when chunks is empty for the no-session case. The former is hard to trigger without injecting a faulty commit; the latter is exercised in `test_generate_raises_no_chunks_when_document_empty` but only with a session factory. Neither is a defect.

4. **`last_text` is assigned but never used after the loop.** Line 300 sets `last_text = response.content` for the last attempt, but the loop only uses it inside the `continue`/`break` path. The variable is dead-code after the loop. Not a bug, but could be removed for cleanliness.

## What I could NOT verify

- **No browser/UI evidence** — this is a backend story, no UI to render.
- **No real LLM call** — the integration tests are not gated by `@pytest.mark.integration` in the diff, and the LLM_PROVIDER is not configured for the test environment. The CLI's `_build_qcm_service` was never run end-to-end against a real LLM. A human should: configure `LLM_PROVIDER=openai` (or `minimax` with `LLM_API_KEY`), upload a sample PDF, then run `python -m ktutor.cli generate-qcm --pseudo <p> --document-id <id> --n 5` and verify the JSON has 5 well-formed questions.
- **No cross-tenant test via the CLI** — the test stub at the CLI layer uses `_StubQcmGenerator` which short-circuits the real generator. The cross-tenant lock is verified at the generator layer; a human should verify the CLI exit code (5) maps correctly by running the manual cross-tenant scenario described in the plan § 10.
- **No Postgres verification** — the model is exercised on SQLite in-memory. `init_db()` is called in `_build_qcm_service`, but no test confirms the table is created in a real Postgres. The plan acknowledges this and defers to s15 (Alembic migration).
- **No test of the `_extract_json_block` regex on edge cases** — e.g., JSON inside a JSON object, JSON preceded by multiple lines of prose, JSON wrapped in a single backtick (not three). The research identified this as a "trap" but the tests only exercise the happy path and the markdown-fence path.

## Final

The story is ready to ship. The implementation is clean, the multi-tenant invariant is locked, the run interdicts are respected, the tests bite where they need to bite, and the coverage threshold is met.

Max severity: minor
Ship allowed: yes
