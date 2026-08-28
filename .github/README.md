# .github

GitHub Actions workflows for the project.

## `workflows/ci.yml`

Runs on every push to `main` and on every pull request targeting `main`. Four jobs:

| Job | Trigger | What it does |
|---|---|---|
| **backend** | Always (if `backend/requirements.txt` exists) | Python 3.12 + pip cache + `pytest --cov` against PostgreSQL 16, MinIO, ChromaDB, and an HTTP stub for DeepSeek-OCR-2 (all as service containers). Coverage gate ≥ 70 %. Linting (ruff) is `continue-on-error` until the linter is enforced. |
| **frontend** | Only if `frontend/package.json` exists | Node 20 + npm cache + `npm ci` + `npm run lint` + `npm run typecheck` + `npm run build`. Lint and typecheck are `continue-on-error` until s11 introduces strict checks. |
| **docs** | Always (if any `docs/**/*.md` exists) | `markdownlint-cli2` on `docs/` and `README.md` with permissive rules (long lines, inline HTML, duplicate link references allowed). |
| **pr-lint** | Only on `pull_request` events | `action-semantic-pull-request` enforces Conventional Commits prefixes (feat, fix, docs, chore, refactor, test) on the PR title. |

## Service containers

The backend job spins up four service containers. The first three (postgres, minio, chroma) come from the project's `docker-compose.yml` images. The fourth (`deepseek-ocr-2`) is a **stub** (`kennethreitz/httpbin`) because the real DeepSeek-OCR-2 service is a heavy GPU model — starting it in CI would cost minutes per run. Tests that need the real OCR are marked `@pytest.mark.integration` and skipped in CI (the `pytest -m "not integration"` filter).

## Why a `markdownlint.jsonc`

The project has many long tables (AC lists, dependency chains), inline HTML (for artifacts in the docs), and cross-references between ADRs and stories. A strict default would drown the CI in noise. The `jsonc` config disables only the rules that conflict with our spec style.
