# Research — Story s23-observabilite-logs-metriques

## The five structuring facts

1. `backend/app/core/logging.py:27-48` — `configure_logging()` configure `loguru` vers stderr mais le payload JSON (`_serialize`) n'inclut pas `request_id`, `pseudo`, `route`, `duration_ms` — ces champs doivent être passés via `extra=` au cas par cas.
2. `backend/app/core/config.py` — pas de variables `OTEL_EXPORTER`, `METRICS_ENABLED`, `LOG_LEVEL` (seul `log_level` existe) ; `.env` et `.env.bak` n'ont pas ces variables non plus.
3. `requirements.txt` — `loguru` n'est pas listé (mais le code `logging.py` l'utilise et il est installé) ; `prometheus-client`, `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi` sont absents du fichier et du code.
4. `docs/stories.md:1082-1095` (s23) — 7 AC couvrent : logs JSON structurés, middleware HTTP, LLM logs, Celery logs, OTEL traces, Prometheus `/metrics`, test. `docs/architecture.md:395-401` et `CLAUDE.md:547-553` confirment la même cible (JSON `loguru`, OTEL console/OTLP, Prometheus `/metrics`, métriques spécifiques).
5. Aucun dossier `backend/app/core/observability/` ni fichier `backend/app/api/metrics.py` n'existe dans le repo actuel (`main` ou worktree `feature/s23-observabilite-logs-metriques`) ; le middleware d'observabilité HTTP et le wrapper LLM tracing sont absents.

---

## Target story

**Story : s23-observabilite-logs-metriques** — Ajouter logs structurés, traces et métriques (complexité 3 dans `docs/stories.md`).

**Acceptance criteria (vérifiés dans `docs/stories.md:1082+`)** :
- [ ] All log lines are JSON-structured (`timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`).
- [ ] All HTTP requests emit a log line with the above fields (FastAPI middleware).
- [ ] All LLM calls emit a log line with `prompt_tokens`, `completion_tokens`, `duration_ms`, `model`.
- [ ] All Celery tasks emit a log line on start, success, and failure.
- [ ] OpenTelemetry traces exported to console (local) and OTLP if `OTEL_EXPORTER=otlp`.
- [ ] Prometheus metrics at `/metrics` (no auth local) : `http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`.
- [ ] A test verifies a sample request produces expected log lines and metrics.

**Dependencies** : toutes les stories API antérieures (s09-s20) — cette story rétrofite le code existant.

---

## Current state of the code

### Observability files
- `backend/app/core/logging.py` — existe (`line 1-49`) ; configure `loguru` JSON vers stderr. Manque `request_id`, `pseudo`, `route`, `duration_ms` dans le payload par défaut (`_serialize` ne les ajoute pas automatiquement).
- `backend/app/core/observability/` — **absent** du repo actuel (`main` et worktree `feature/s23-observabilite-logs-metriques`).
- `backend/app/api/metrics.py` — **absent** (aucun endpoint `/metrics`).
- `backend/app/core/config.py` — `log_level: str = "INFO"` (`line 23`) et `debug: bool = False` (`line 23`) existent ; `OTEL_EXPORTER`, `METRICS_ENABLED`, `LOG_LEVEL` (le nom exact du `CLAUDE.md`) sont absents.

### Middleware et main
- `backend/app/main.py` (`line 1-86`) — `CORSMiddleware` monté (`line 68-74`), aucun middleware de logging HTTP (durée, `request_id`) ni initialisation OTEL dans le `lifespan` (`line 39-57`).
- `backend/app/api/chat/router.py` (`line 198-300`) — pas de log structuré avec `duration_ms` ni `request_id` au niveau du router ; seul un `logger.warning` dans `_persist_conversation` (`line 169`).
- `backend/app/services/llm/client.py` (`line 1-104`) — pas de log des appels LLM (`invoke`/`astream`) avec `duration_ms`, `model`, `prompt_tokens`, `completion_tokens`.
- `backend/app/services/agents/supervisor.py` (`line 1-...`) — pas de tracing OTEL sur les transitions de noeud.
- `backend/app/services/rag/chroma_store.py` — pas de métrique `rag_retrievals_total`.

### Tests
- `backend/tests/` (`line 1-...`) — aucun test ne mentionne `metrics`, `prometheus`, `loguru` (vérifié par `grep -r`).

### Packages
- `requirements.txt` (`line 1-...)` — `loguru` absent (le code le requiert et il est installé dans l'environnement), `prometheus-client`, `opentelemetry-*`, `celery` absents.
- `.env` et `.env.bak` (`line 1-48`) — pas de `OTEL_EXPORTER`, `METRICS_ENABLED`, `LOG_LEVEL`.

---

## Anchor points

**Où le feature s'insère dans le code actuel :**

- `backend/app/core/observability/` — nouveau dossier (log, trace, métriques, alertes). À créer.
- `backend/app/core/logging.py` — doit être étendu (ou remplacé) pour ajouter `request_id` (via `contextvars` ou `extra`), `pseudo`, `route`, `duration_ms`.
- `backend/app/main.py` — ajouter un middleware FastAPI qui loggue chaque requête avec les champs requis (`request_id`, `route`, `duration_ms`, `pseudo` si JWT présent). Ajouter initialisation OTEL (`tracer_provider`) dans le `lifespan`. Monter le router `/metrics` (via `backend/app/api/metrics.py` à créer).
- `backend/app/services/llm/client.py` — wrapper autour de `invoke` et `astream` pour logguer `duration_ms`, `model`, `prompt_tokens`, `completion_tokens` (si disponibles via `usage_metadata` du modèle OpenAI-compatible).
- `backend/app/services/agents/supervisor.py` — ajouter tracing OTEL autour de `ask` et `astream` (ou autour du dispatcher).
- `backend/app/services/rag/retriever.py` — ajouter compteur `rag_retrievals_total` (Prometheus).
- `backend/app/core/config.py` — ajouter `ot_exporter`, `metrics_enabled`, `log_level` (le nom exact `LOG_LEVEL` du `CLAUDE.md` doit être aligné avec `log_level` existant — vérifier la cohérence).
- `backend/app/api/chat/router.py` et autres routers — s'assurer que chaque route passe le `request_id` au logger.

---

## Verified APIs / functions

- `app.core.logging.configure_logging()` (`logging.py:27`) — existe, configure `loguru` vers stderr avec format JSON (`_serialize`). Ne loggue pas automatiquement `request_id`, `pseudo`, `route`, `duration_ms`.
- `app.core.config.get_settings()` (`config.py:177`) — singleton Pydantic settings. Pas de `OTEL_EXPORTER` ni `METRICS_ENABLED`.
- `FastAPI(...)` dans `main.py:62` — pas de middleware d'observabilité.
- `SubjectSupervisor.ask()` / `.astream()` — pas de tracing OTEL.
- `LlmClient.invoke()` / `.astream()` — pas de log des métriques LLM.
- Aucun endpoint `/metrics` (fichier `metrics.py` absent, aucune référence `prometheus_client` dans le code).

---

## Traps & constraints

- `loguru` est utilisé dans le code (`logging.py`) mais **absent de `requirements.txt`** — il doit être ajouté (ou le code doit être aligné si un autre package est prévu). Vérifier si `loguru` est bien le package attendu par `CLAUDE.md` (oui, `CLAUDE.md:549` mentionne `loguru` pour Python).
- Le middleware d'observabilité HTTP doit être ajouté **sans casser le streaming SSE** (`StreamingResponse` dans `chat/router.py`). Un middleware qui lit le body ou bloque le stream peut corrompre le format `text/event-stream`.
- `OTEL_EXPORTER` doit être lu depuis `.env` ; le `CLAUDE.md` mentionne `console` (défaut) et `otlp`. Le `main.py` doit initialiser le tracer selon cet env.
- `prometheus_client` doit être ajouté à `requirements.txt` et importé dans `metrics.py`. L'exposition `/metrics` doit être **sans auth** en local (`CLAUDE.md:551`).
- Les métriques `http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total` doivent être des compteurs Prometheus (pas de simples variables Python).
- Les tâches Celery : le code actuel (`backend/app/services/`) n'a pas de dossier `tasks.py` ni d'import Celery dans le backend. Vérifier si `celery` est utilisé ailleurs (le `docker-compose.yml` mentionne Celery). Le log Celery doit s'intégrer au middleware existant ou au wrapper `loguru`.
- `request_id` doit être propagé entre le middleware HTTP et le logger `loguru` ; utiliser `contextvars` est la convention recommandée (`CLAUDE.md:162`).
- La story rétrofite toutes les routes antérieures (s09-s20) — le middleware doit être monté globalement (`main.py`) pour couvrir tous les endpoints sans modifier chaque router individuellement.

---

## Open questions

1. **Celery tasks** : le backend a-t-il des tâches Celery définies ? (`docker-compose.yml` mentionne `celery` mais aucun fichier `tasks.py` ou `celery_app` n'est visible dans le code actuel). Faut-il créer le wrapper Celery dans cette story ou considérer que le log Celery est hors périmètre immédiat ?
2. **`request_id` source** : doit-on générer un UUID par requête dans le middleware, ou réutiliser un `X-Request-ID` envoyé par le client (frontend) ? La convention `CLAUDE.md` suggère `request_id` dans le log mais ne précise pas la source.
3. **`metrics.py` emplacement** : doit-on créer un `backend/app/api/metrics.py` (router monté dans `main.py`) ou un module `backend/app/core/observability/metrics.py` appelé par un endpoint séparé ? `docs/architecture.md:61` mentionne `app/api/metrics.py`.
4. **`log_level` vs `LOG_LEVEL`** : `CLAUDE.md:588` mentionne `LOG_LEVEL=INFO` dans `.env.example`, mais le code actuel (`config.py`) utilise `log_level`. Doit-on aligner le nom (`log_level`) ou ajouter `LOG_LEVEL` comme alias ?
5. **Tests** : doit-on écrire un test d'intégration (HTTP + Prometheus `/metrics`) ou un test unitaire du middleware/log ? L'AC demande « a test verifies a sample request produces the expected log lines and metrics » — un test d'intégration avec `httpx` + `TestClient` semble le plus direct.

---

## Real complexity

**Score dans `docs/stories.md` : 3** — après lecture du code actuel, le score reste **3** (pas de changement). Justification :

- Le code actuel (`logging.py`) est déjà partiellement structuré (JSON via `loguru`) — cela réduit le travail par rapport à un départ de zéro.
- Cependant, le middleware HTTP, le wrapper LLM, le tracing OTEL, le endpoint `/metrics`, et le test sont **absents** — cela représente 5 tâches indépendantes (middleware, LLM log, OTEL, metrics, test), ce qui correspond bien à un score 3 (plus qu'une simple correction, moins qu'une refonte architecturale).
- Aucune dépendance bloquante (les routes existent, le middleware peut être monté globalement, le `loguru` est déjà présent).
- **Pas de proposition de split** nécessaire (le score 3 est cohérent, la story est réalisable en un cycle complet).

---

## Split proposal

Non requis (complexité 3, cohérente avec le code vérifié). Si le plan dépasse 10 tâches ou rencontre un blocage majeur (ex : absence de `celery` dans le code actuel rendant le log Celery impossible), la split recommandée serait :
- `s23a-observabilite-logs-middleware` — middleware HTTP + LLM wrapper log + OTEL traces.
- `s23b-observabilite-metriques` — Prometheus `/metrics` + test + documentation.

Pour l'instant, **pas de split** — continuer avec `s23-observabilite-logs-metriques`.

---

## Files read during research (worktree `feature/s23-observabilite-logs-metriques`)

- `docs/stories.md` (story s23, AC, dependencies)
- `docs/architecture.md` (stack, patterns, observabilité, metrics endpoint)
- `AGENTS.md` (conventions log, test, multi-tenancy)
- `CLAUDE.md` (observabilité, variables env, conventions log)
- `backend/app/core/logging.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/api/chat/router.py`
- `backend/app/services/llm/client.py`
- `backend/app/services/agents/supervisor.py`
- `requirements.txt`
- `.env`, `.env.bak`
- `docs/research/` (vérifié vide avant écriture)

---
*Recherche terminée. Aucune prémisse fausse détectée (le code actuel est partiellement structuré mais très incomplet par rapport aux AC s23). Prochaines étapes : `/ks-plan s23-observabilite-logs-metriques` (après validation du plan) puis `/ks-execute s23-observabilite-logs-metriques`.*
