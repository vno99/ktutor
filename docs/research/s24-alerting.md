# Research — Story s24-alerting

## The five structuring facts

1. `backend/app/core/observability/metrics.py:6-16` — 5 compteurs Prometheus existent (`http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`) ; aucun compteur `celery_queue_length` et aucun fichier `alerts.py`.
2. `backend/app/core/observability/middleware.py:18-50` — middleware natif FastAPI monté dans `main.py`; loggue chaque requête avec `request_id`, `route`, `duration_ms`, `pseudo`; incrémente `http_requests_total` et `http_request_duration_seconds`.
3. `backend/app/main.py:80` — `ObservabilityMiddleware` monté (`add_middleware`) ; `metrics_router` monté (`line 90`) ; `setup_tracing()` initialisé dans le `lifespan` (`line 61`). Aucun système d'alerte initialisé.
4. `docs/stories.md:1118-1145` (s24) — 5 AC : 3 règles d'alerte Prometheus (taux d'erreur 5xx > 5% sur 2 min, p95 latency > 5s sur 5 min, Celery queue > 100 tâches), affichage console (`ALERT` log line), test synthétique 5xx storm.
5. `docs/research/s23-observabilite-logs-metriques.md` (présent dans le worktree s24) — la recherche s23 confirme que `metrics.py`, `middleware.py`, `main.py` et `tracing.py` existent et fonctionnent ; le dossier `observability/` est le point d'ancrage.

---

## Target story

**Story : s24-alerting** — Configurer des alertes sur les signaux critiques (complexité 2 dans `docs/stories.md`).

**Acceptance criteria (vérifiés dans `docs/stories.md:1126-1132`)** :
- [ ] Alert rule `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05` for 2 min.
- [ ] Alert rule `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5` for 5 min.
- [ ] Alert rule `celery_queue_length > 100`.
- [ ] Console output (`ALERT` log line) for POC — no PagerDuty / Slack.
- [ ] Synthetic 5xx storm test verifies alert fires within 2 min.

**Dependencies** : s23 (observability infrastructure exists — merged in PR #29, commit `7b51865`).

---

## Current state of the code

### Observability files (worktree `feature/s24-alerting`)
- `backend/app/core/observability/metrics.py` — 5 compteurs définis (`Counter` Prometheus). Aucun `alerts.py` dans le dossier.
- `backend/app/core/observability/middleware.py` — middleware natif monté dans `main.py` (`line 80`). Aucune logique d'alerte.
- `backend/app/core/observability/tracing.py` — OTEL initialisé (`setup_tracing()` dans `main.py:61`).
- `backend/app/core/observability/celery_logger.py` — wrapper Celery prêt mais aucune tâche enregistrée (`ImportError` catché). Aucune métrique de file d'attente Celery.
- `backend/app/core/observability/__init__.py` — expose `metrics`, `tracing`.

### Metrics endpoint
- `backend/app/api/metrics.py` — endpoint `GET /metrics` monté (`main.py:90`). Expose `generate_latest()` (tous les compteurs enregistrés dans le registre global Prometheus).
- Le `metrics.py` du worktree s24 ne contient pas d'import explicite des compteurs (ils sont enregistrés dans le registre global via le module `metrics.py`). L'import dans `metrics.py` doit être maintenu (déjà corrigé dans s23 avec `# noqa: F401`).

### Tests
- `backend/tests/core/test_observability.py` — 4 tests (`test_settings_has_observability_vars`, `test_observability_module_exists`, `test_llm_wrapper_logs_duration`, `test_metrics_endpoint_exists`, `test_main_has_observability_middleware`, `test_celery_wrapper_imports`). Aucun test d'alerte.
- `docs/research/s23-observabilite-logs-metriques.md` (présent) confirme que le middleware, le wrapper LLM, le tracing et le endpoint `/metrics` fonctionnent.

### Alert rules (absent)
- Aucun fichier `alerts.yml`, `prometheus/alerts.yml`, ou `ops/prometheus/` dans le repo.
- Aucune référence à `ALERT` dans le code actuel (`grep -r "ALERT" backend/app/` donne 0 résultat dans le worktree s24).
- Aucune métrique `celery_queue_length` dans `metrics.py`.

---

## Anchor points

**Où le feature s'insère dans le code actuel :**

- `backend/app/core/observability/alerts.py` — nouveau fichier (règles d'alerte + logique de déclenchement console).
- `backend/app/core/observability/metrics.py` — ajouter le compteur `celery_queue_length` (`Counter` Prometheus).
- `backend/app/main.py` — initialiser le système d'alerte dans le `lifespan` (ou au démarrage), sans bloquer le stream SSE.
- `backend/app/core/observability/middleware.py` — le middleware loggue chaque requête ; les alertes doivent lire ces métriques (ou être déclenchées par un processus séparé). Pour le POC, un log `ALERT` dans le middleware (si le taux dépasse le seuil) ou dans un thread de vérification périodique suffit.
- `tests/core/test_observability.py` — ajouter `test_alert_fires_on_5xx_storm` (ou `test_alert_console_output`).
- `docs/plans/s24-alerting.md` (à créer) — plan validé (`validated: yes`) avant `execute`.

---

## Verified APIs / functions

- `metrics.http_requests_total` (`metrics.py:6`) — `Counter` avec labels `method`, `route`.
- `metrics.http_request_duration_seconds` (`metrics.py:9`) — `Counter` avec labels `method`, `route`.
- `metrics.llm_calls_total` (`metrics.py:12`) — `Counter` avec label `model`.
- `metrics.llm_call_duration_seconds` (`metrics.py:14`) — `Counter` avec label `model`.
- `metrics.rag_retrievals_total` (`metrics.py:16`) — `Counter` sans label.
- `ObservabilityMiddleware.dispatch()` (`middleware.py:19`) — loggue chaque requête et incrémente `http_requests_total` / `http_request_duration_seconds`.
- `main.lifespan()` (`main.py:42`) — initialise `init_db()` et `setup_tracing()`.
- `main.app` (`main.py:67`) — `FastAPI` avec middleware monté.
- `metrics_router` (`api/metrics.py`) — `GET /metrics` monté (`main.py:90`).
- Aucun fichier `alerts.py` dans `core/observability/` ; aucune référence `ALERT` dans le backend.
- `celery_logger.init_celery_logger()` (`celery_logger.py:7`) — wrapper prêt mais aucune tâche Celery enregistrée dans le backend (vérifié : `find backend/app/services -name "*celery*"` donne `celery_logger.py` uniquement ; aucun `tasks.py`).

---

## Traps & constraints

- **Aucun blocage sur le middleware** : le middleware doit rester natif (`BaseHTTPMiddleware`) et ne pas interférer avec le streaming SSE (`StreamingResponse`). Le `try/except` vide a été supprimé dans s23 (`middleware.py:32` corrigé) ; il ne reste aucun `except Exception: pass`.
- **Compteur `celery_queue_length`** : doit être un `Counter` Prometheus (`metrics.py`). Pour le POC, la valeur peut être mise à jour manuellement (ex. dans le wrapper Celery ou dans un script de simulation). La métrique doit exister même si aucune tâche Celery n'est enregistrée (`metrics.py` l'enregistre dans le registre global).
- **Test 5xx storm** : difficile à simuler avec `pytest` seul. Utiliser un `httpx` loop ou `TestClient` avec des réponses synthétiques `500`. Vérifier que le log `ALERT` apparaît dans `caplog` (ou dans le fichier de log). Le test doit être rapide (< 5s) et ne pas nécessiter un vrai 5xx upstream.
- **Dépendance s23** : le PR #29 (`s23-observabilite-logs-metriques`) est fusionné dans `main` (`commit 7b51865` dans le worktree s24). Aucune dépendance bloquante.
- **Pas d'invention de composant UI** : s24 est pure infrastructure backend (`docs/designs/s24-alerting.md` doit confirmer : pas d'écran). Ne pas créer de `frontend/components/ObservabilityPanel.tsx`.
- **Le `.env` et `requirements.txt` doivent rester cohérents** : `metrics.py` utilise `prometheus_client` (déjà ajouté dans `requirements.txt` en s23). Aucune nouvelle dépendance requise pour s24 (sauf si `prometheus_client` n'est pas présent — vérifier dans le worktree s24).

---

## Open questions

1. **Comment récupérer `celery_queue_length`** ? Le backend n'a pas de `tasks.py` ni d'import Celery dans le code actuel (`find backend/app/services -name "*celery*"` donne `celery_logger.py` uniquement). Doit-on créer un compteur manuel dans `metrics.py` et le mettre à jour dans `celery_logger.py` (même sans tâches) ? Ou considérer que la métrique est présente mais toujours à `0` jusqu'à l'introduction des tâches ? L'AC exige `celery_queue_length > 100` — cela suggère que le compteur doit exister et être mis à jour.
2. **Déclenchement de l'alerte** : doit-on créer un processus de vérification périodique (ex. `threading.Timer` ou un endpoint `/api/ops/check_alerts`) ou déclencher l'alerte directement dans le middleware (ex. si `rate > 0.05` après chaque requête) ? Le middleware actuel (`middleware.py`) ne fait pas de calcul de taux — il loggue chaque requête individuellement. Un calcul de taux (`rate(...) > 0.05`) nécessite un agrégateur (Prometheus) ou un calcul en mémoire (ex. un compteur avec un `time_window`). Pour le POC, le plus simple est un script de vérification (`alerts.py`) qui lit le registre Prometheus (`prometheus_client`) et loggue `ALERT` si le seuil est dépassé.
3. **`ops/prometheus/alerts.yml`** : le story mentionne ce fichier dans les agentic notes (`docs/stories.md:1139`). Doit-on le créer dans le worktree (même si le POC n'utilise pas Alertmanager) ? Ou le documenter dans le plan sans le créer ? L'AC ne mentionne pas explicitement le fichier `alerts.yml` — il mentionne les règles d'alerte et le log console. Pour le POC, le fichier `alerts.yml` est optionnel (le `CLAUDE.md:400` mentionne `docs/decisions/` ou `ops/prometheus/alerts.yml`). Recommandation : créer `docs/plans/s24-alerting.md` avec la mention du fichier `alerts.yml` (à créer si nécessaire), mais pour le POC, se concentrer sur le code Python (`alerts.py`) et le test.

---

## Real complexity

**Score dans `docs/stories.md` : 2** — après lecture du code actuel (`metrics.py`, `middleware.py`, `main.py`, `celery_logger.py`, `tests/core/test_observability.py`, `docs/research/s23-observabilite-logs-metriques.md`), le score reste **2** (cohérent, pas de changement majeur nécessaire).

Justification :
- Le code actuel (`s23` fusionné) fournit déjà le middleware, le wrapper LLM, le tracing, le endpoint `/metrics`, et le dossier `core/observability/`.
- La création de `alerts.py`, du compteur `celery_queue_length`, et du test d'alerte représente 3-4 tâches indépendantes, cohérent avec un score 2.
- Aucune dépendance bloquante (`main` a le middleware monté, `metrics.py` a les compteurs, `tests/core/test_observability.py` existe).
- **Pas de split** nécessaire (le score 2 est cohérent avec le périmètre et le code actuel).

---

## Split proposal

Non requis (complexité 2, cohérente avec le code vérifié et les AC). Si le plan dépasse 10 tâches ou si le test 5xx storm s'avère impossible sans un vrai serveur 5xx, la split recommandée serait :
- `s24a-observabilite-alert-rules` — création `alerts.py`, compteur `celery_queue_length`, règles Prometheus dans `alerts.yml`.
- `s24b-observabilite-alert-test` — test synthétique 5xx storm + vérification log `ALERT`.

Pour l'instant, **pas de split** — continuer avec `s24-alerting`.

---

## Files read during research (worktree `feature/s24-alerting`)

- `docs/stories.md` (story s24, AC, dependencies : s23)
- `docs/architecture.md` (stack, patterns, observabilité, alerting)
- `AGENTS.md` (conventions pipeline, log, tests, multi-tenancy)
- `CLAUDE.md` (observabilité, variables env, conventions log, alerting)
- `backend/app/core/observability/metrics.py` (5 compteurs existants)
- `backend/app/core/observability/middleware.py` (middleware natif, aucun try/except vide restant)
- `backend/app/core/observability/tracing.py` (OTEL, pas d'import `os` inutilisé)
- `backend/app/core/observability/celery_logger.py` (wrapper prêt, pas d'import `celery` inutilisé)
- `backend/app/core/observability/__init__.py` (`metrics`, `tracing` exposés)
- `backend/app/main.py` (middleware monté, router metrics monté, OTEL initialisé)
- `backend/app/api/metrics.py` (endpoint `/metrics` monté, imports triés, `# noqa: F401` sur les compteurs)
- `docs/research/s23-observabilite-logs-metriques.md` (recherche précédente, confirme le code et les pièges)
- `docs/plans/s23-observabilite-logs-metriques.md` (plan validé `validated: yes`, 8 tâches cochées)
- `docs/reviews/s23-observabilite-logs-metriques.md` (`Max severity: none`, `Ship allowed: yes`)
- `backend/app/core/config.py` (`log_level`, `metrics_enabled`, `ot_exporter` non vérifiés directement dans le worktree s24 mais hérités du code s23 fusionné)
- `requirements.txt` (vérifié indirectement : `prometheus_client` présent dans le code et le PR s23)

---

## Verified facts against code (worktree `feature/s24-alerting`)

1. `metrics.py` existe (`line 1-17`), 5 compteurs (`Counter`) définis. Aucun `celery_queue_length`.
2. `middleware.py` existe (`line 1-51`), middleware natif, aucun `try/except` vide, aucun `except Exception: pass`.
3. `main.py` (`line 80`) — `ObservabilityMiddleware` monté ; `line 90` — `metrics_router` monté ; `line 61` — `setup_tracing()` initialisé dans `lifespan`.
4. `tests/core/test_observability.py` — 7 tests (`test_settings_has_observability_vars`, `test_observability_module_exists`, `test_llm_wrapper_logs_duration`, `test_tracing_exists`, `test_celery_wrapper_imports`, `test_metrics_endpoint_exists`, `test_main_has_observability_middleware`, `test_log_json_has_request_fields`). Aucun test d'alerte.
5. `docs/research/s23-observabilite-logs-metriques.md` présent dans le worktree s24 (hérité du repo principal) — confirme le périmètre s23 et la base technique.
6. Aucun `docs/plans/s24-alerting.md` ni `docs/reviews/s24-alerting.md` dans le worktree s24 — à créer via le pipeline (`/ks-plan` puis `/ks-execute` puis `/ks-review`).
7. `AGENTS.md` (lu dans le worktree s24) — pipeline `Research → Design → Plan → Execute → Review → Ship` obligatoire ; pas de code direct sans plan validé (`validated: yes`).

---

*Recherche terminée. Aucune prémisse fausse détectée (le code actuel (`main` fusionné avec s23) fournit la base d'observabilité complète ; la story s24 ajoute les alertes et le test synthétique). Prochaines étapes : `/ks-plan s24-alerting` (après validation du plan) puis `/ks-execute s24-alerting`.*
