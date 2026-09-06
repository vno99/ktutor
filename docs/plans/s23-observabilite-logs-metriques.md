---
validated: yes
---
# Plan — Story s23-observabilite-logs-metriques

Branch: `feature/s23-observabilite-logs-metriques`
Research: `docs/research/s23-observabilite-logs-metriques.md` — lu en premier ; ce plan ne répète pas la recherche.

## Target story

**Story s23-observabilite-logs-metriques** — Ajouter logs structurés (`loguru` JSON avec `request_id`, `pseudo`, `route`, `duration_ms`), traces OpenTelemetry (console / OTLP selon `OTEL_EXPORTER`), métriques Prometheus (`/metrics`, 5 compteurs) et un test d'intégration.

**Acceptance criteria (7, de `docs/stories.md:1082+`)** :
1. Tous les logs sont JSON structurés (`timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`).
2. Toutes les requêtes HTTP émettent un log avec ces champs (middleware FastAPI).
3. Tous les appels LLM émettent un log avec `prompt_tokens`, `completion_tokens` (si dispo), `duration_ms`, `model`.
4. Toutes les tâches Celery émettent un log au démarrage, succès et échec.
5. Traces OTEL exportées console (local) et OTLP si `OTEL_EXPORTER=otlp`.
6. Métriques Prometheus sur `/metrics` (sans auth local) : `http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`.
7. Un test vérifie qu'une requête échantillon produit les lignes de log et métriques attendues.

**Dépendances** : toutes les stories API antérieures (s09-s20) — rétrofit du code existant. Pas de dépendance bloquante sur des branches non mergées : `main` contient déjà `logging.py`, `main.py`, `llm/client.py`, `supervisor.py`, `chat/router.py`.

---

## Tasks (ordered)

1. [x] **Ajouter les variables env et mettre à jour `requirements.txt`** — `OTEL_EXPORTER`, `METRICS_ENABLED`, `LOG_LEVEL` dans `.env` et `config.py` (aligner `log_level` existant avec `LOG_LEVEL`) ; ajouter `prometheus-client`, `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp-proto-grpc` (ou `otlp`) et `loguru` dans `requirements.txt`. Vérifier que `python -c "import loguru, prometheus_client, opentelemetry"` passe.

2. [x] **Créer `backend/app/core/observability/` et initialiser OTEL dans le middleware** — dossier avec `__init__.py`, `tracing.py` (setup `TracerProvider` + `ConsoleSpanExporter` + `OTLPSpanExporter` conditionnel sur `OTEL_EXPORTER`), `metrics.py` (définition des 5 compteurs Prometheus). Modifier `main.py` : ajouter le middleware de logging HTTP (`request_id` généré par UUID, `duration_ms` mesuré, `route` et `pseudo` extraits du JWT) et initialiser OTEL dans le `lifespan`. Vérifier que `main.py` importe correctement sans erreur au démarrage (`python -c "from app.main import app"`).

3. [x] **Étendre `logging.py` pour le payload structuré complet** — modifier `_serialize` (ou le `filter`) pour injecter systématiquement `request_id`, `pseudo`, `route`, `duration_ms` dans le payload JSON. Utiliser un `contextvars.ContextVar` (ou passer `extra=` au logger) pour propager ces champs depuis le middleware HTTP. Vérifier que chaque ligne de log émise par le middleware contient bien ces 4 champs.

4. [x] **Wrapper LLM — log des appels** — dans `backend/app/services/llm/client.py`, envelopper `invoke` et `astream` avec un bloc `try/finally` (ou `with`) qui loggue `duration_ms` (via `time.monotonic()`), `model` (`settings.llm_model`), et si disponible `usage_metadata.prompt_tokens` / `completion_tokens` depuis le résultat `AIMessage` (vérifier la présence de `.usage_metadata` dans le retour `ChatOpenAI`). Vérifier avec un appel manuel (`python -c "from app.services.llm.client import build_llm_client; ..."`) que le log apparaît.

5. [x] **Tracer OTEL sur le superviseur et le RAG** — dans `backend/app/services/agents/supervisor.py`, ajouter `with tracer.start_as_current_span(...)` autour de `ask` et `astream`. Dans `backend/app/services/rag/retriever.py` (ou `chroma_store.py`), ajouter un `span` autour de la récupération de chunks (`get_chroma_collection`). Vérifier que la trace apparaît dans la console (`console` exporter) après un appel au chat.

6. [x] **Endpoint /metrics et métriques Prometheus** — créer `backend/app/api/metrics.py` avec le router `GET /metrics` (pas d'auth requise en local, conformément à l'AC). Exposer au moins 5 compteurs (`http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`). Monter le router dans `main.py`. Vérifier que `curl http://localhost:8000/metrics` renvoie les métriques au format Prometheus.

7. [x] **Log Celery (si tâches existantes)** — vérifier si des tâches Celery existent dans le repo (`find backend/app/services -name "*celery*" -o -name "*task*"`). Si aucune tâche n'existe dans le code actuel (le `docker-compose.yml` mentionne Celery mais aucun `tasks.py`), créer un wrapper minimal (`app/core/observability/celery_logger.py`) qui intercepte le signal `before_task_publish`, `after_task_publish` et loggue au format JSON. Si aucune tâche n'est définie, documenter dans le code (`celery_logger.py`) que le wrapper est prêt mais qu'aucune tâche n'est encore enregistrée — cela satisfait l'AC sans inventer de tâches fictives. Vérifier que le wrapper s'importe sans erreur (`python -c "from app.core.observability.celery_logger import ..."`).

8. [x] **Test d'intégration** — créer `backend/tests/core/test_observability.py` (ou ajouter au fichier existant `tests/core/` si présent). Le test doit : lancer le `FastAPI` avec `TestClient`, faire une requête `POST /api/chat/stream` (ou `GET` simple), vérifier que le log JSON contient `timestamp`, `level`, `message`, `request_id`, `route`, `duration_ms` ; vérifier que `GET /metrics` renvoie au moins `http_requests_total`. Utiliser `pytest` et `caplog` (ou `caplog` de `loguru`) pour capturer le log. Le test doit passer (`pytest -v backend/tests/core/test_observability.py`).

---

## Run interdicts

- **Le middleware HTTP doit rester un middleware FastAPI natif** (`app.add_middleware`) et non un décorateur manuel sur chaque endpoint — cela couvre toutes les routes (chat, documents, auth, etc.) sans modifier chaque router individuellement.
- **Le wrapper LLM doit rester dans `llm/client.py`** (pas dans le superviseur ni le router) — le wrapper encapsule le `LlmClient` Protocol et ne modifie pas la logique de routage ou la réponse SSE.
- **Le `core/observability/` doit être un nouveau dossier** (pas remplacer `logging.py`) — `logging.py` reste le point d'entrée du logger ; `core/observability/` ajoute la couche OTEL + métriques.
- **Aucun nouveau composant UI ne doit être inventé** — s23 n'a pas d'écran utilisateur (`docs/designs/s23-observabilite-logs-metriques.md` confirme : pas de `Button`, `Card`, `Header`). Ne pas créer de `frontend/components/ObservabilityPanel.tsx` ou autre.
- **Le `.env` et `requirements.txt` doivent être modifiés dans le worktree** (`feature/s23-observabilite-logs-metriques`) — pas dans la branche `main` directement.
- **Le `docs/research/s23-observabilite-logs-metriques.md` et `docs/designs/s23-observabilite-logs-metriques.md` doivent rester intacts** (pas de réécriture) — le plan ne remplace pas la recherche ni le design.
- **Pas de changement sur la base de données** (`models.py`, migrations) — l'observabilité n'ajoute pas de table métier (les métriques sont en mémoire via Prometheus, pas persistées).
- **Pas d'invention de nouvelles tâches Celery** — si aucune tâche n'existe, le wrapper doit être prêt mais pas créer de tâche fictive pour passer le test.

---

## The point everything turns on

Le plan repose sur le fait que le middleware FastAPI (`app.add_middleware`) peut capturer `request_id`, `route`, `duration_ms` et `pseudo` (via `Depends(get_current_user)`) sans bloquer le streaming SSE. Si le middleware lit le body ou bloque le stream, `/api/chat/stream` casse. Vérifier : le middleware doit être un middleware `BaseHTTPMiddleware` (ou `middleware` natif) qui n'interfère pas avec le `StreamingResponse` ; la mesure de durée doit être faite via `time.time()` avant et après `await call_next(request)`. Comparer avec le middleware `CORSMiddleware` actuel (`main.py:68`) — le même pattern doit s'appliquer.

Le deuxième point critique : le wrapper LLM (`llm/client.py`) doit accéder à `usage_metadata` sans lever d'exception si le champ est absent (certains modèles ou configurations ne renvoient pas `usage_metadata`). Le code doit être défensif : `if hasattr(result, "usage_metadata") and result.usage_metadata: ...`. Vérifier avec un appel manuel au client.

Le troisième point : le `core/observability/` doit s'importer sans erreur même si `OTEL_EXPORTER` est non défini dans `.env` (défaut `console`). Vérifier : `tracing.py` doit initialiser un `TracerProvider` par défaut sans dépendre de variables d'environnement obligatoires.

---

## Files touched

- `.worktrees/s23-observabilite-logs-metriques/docs/plans/s23-observabilite-logs-metriques.md` (ce fichier)
- `.worktrees/s23-observabilite-logs-metriques/docs/research/s23-observabilite-logs-metriques.md` (lecture uniquement, pas de modification)
- `.worktrees/s23-observabilite-logs-metriques/docs/designs/s23-observabilite-logs-metriques.md` (lecture uniquement)
- `backend/app/core/logging.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/core/observability/` (nouveau dossier : `__init__.py`, `tracing.py`, `metrics.py`, `celery_logger.py` optionnel)
- `backend/app/api/metrics.py` (nouveau)
- `backend/app/services/llm/client.py`
- `backend/app/services/agents/supervisor.py`
- `backend/app/services/rag/retriever.py` ou `chroma_store.py` (pour le compteur `rag_retrievals_total`)
- `requirements.txt`
- `.env` (ou `.env.example` si `.env` est gitignored — vérifier)
- `backend/tests/core/test_observability.py` (nouveau test)

---

## Test strategy

- **Niveau unitaire (test par AC)** : un test par AC dans `backend/tests/core/test_observability.py` :
  - `test_log_json_has_all_fields` : lance un `FastAPI` avec `TestClient`, fait un `GET /api/chat/stream` (ou `POST` si le router l'exige — utiliser le même format que `test_chat_stream.py` existant dans `backend/tests/api/test_chat_stream.py`), capture le log via `caplog` (ou `logger.add` temporaire) et vérifie que le JSON contient `timestamp`, `level`, `message`, `request_id`, `route`, `duration_ms`.
  - `test_metrics_endpoint` : `GET /metrics` et vérifie que le texte de réponse contient `http_requests_total` et au moins un autre compteur (`llm_calls_total` ou `rag_retrievals_total`).
  - `test_llm_wrapper_logs_duration` : mock du `BaseChatModel` (via `FakeListLLM` de LangChain ou stub manuel) et vérifie que le log contient `duration_ms` et `model`.
  - `test_celery_wrapper_imports` (si tâches existantes) : vérifie que le wrapper s'importe (`from app.core.observability.celery_logger import ...`) et que le signal `before_task_publish` est enregistré.
- **Pas de test d'intégration complet** (pas de base PostgreSQL nécessaire au-delà du `TestClient` — utiliser le même schéma que `test_chat_stream.py` qui utilise `init_db()` et des fixtures).
- **Pas de test d'isolation cross-tenant** obligatoire (s23 ne manipule pas de données élève — le middleware loggue le `pseudo` mais ne le compare pas à une URL/body ; l'isolation reste couverte par s09-s20).
- **Aucun test frontend Playwright** nécessaire (pas d'écran UI pour s23 — `docs/designs/s23-observabilite-logs-metriques.md` confirme).

---

## Definition of Done

- [ ] `docs/plans/s23-observabilite-logs-metriques.md` validé (`validated: yes`).
- [ ] `docs/research/s23-observabilite-logs-metriques.md` lu (existe, 141 lignes, vérifié par recherche).
- [ ] `docs/designs/s23-observabilite-logs-metriques.md` et `.html` lus (design confirmé : pas d'écran UI, pas de composant inventé).
- [ ] Toutes les tâches (1-8) cochées dans le plan, avec un commit par tâche ou un commit unique portant toutes les modifications (selon la convention du projet — `AGENTS.md` : un commit par story, pas un par tâche).
- [ ] Le middleware HTTP loggue chaque requête avec `request_id`, `route`, `duration_ms`, `pseudo`.
- [ ] `backend/app/core/observability/` existe avec `tracing.py`, `metrics.py`, et le wrapper Celery (si applicable).
- [ ] `backend/app/api/metrics.py` répond sur `/metrics` avec au moins 5 compteurs Prometheus.
- [ ] `llm/client.py` loggue chaque appel LLM (durée, modèle, tokens si dispo).
- [ ] `main.py` initialise OTEL et monte le middleware sans erreur au démarrage.
- [ ] `requirements.txt` et `.env` mis à jour (packages + variables).
- [ ] `backend/tests/core/test_observability.py` passe (`pytest -v` exit 0).
- [ ] Aucune régression sur le code existant (`main.py`, `logging.py`, `chat/router.py`, `llm/client.py`) — vérifier avec `pytest backend/tests/` (tests existants toujours verts).
- [ ] Aucune donnée personnelle (mot de passe, token, contenu document) dans les logs (convention `CLAUDE.md:161`).
- [ ] `docs/reviews/s23-observabilite-logs-metriques.md` rédigé et terminé par `Max severity: ...` + `Ship allowed: yes/no`.

---
*Plan prêt. Prochaines étapes : validation (`/ks-plan s23-observabilite-logs-metriques` avec réponse "Validate"), puis `/ks-execute s23-observabilite-logs-metriques` (délégation au sous-agent `implementer` dans le worktree).*
