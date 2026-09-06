# Review — s24-alerting

## Verdict
Max severity: none
Ship allowed: yes

## Findings
- `alerts.py` créé avec 3 règles Prometheus et console `ALERT`.
- `metrics.py` : compteur `celery_queue_length` ajouté.
- `main.py` : initialisation alertes dans `lifespan` (non bloquant).
- `tests/core/test_observability.py` : `test_alert_fires_on_5xx_storm` et `test_alert_console_output` ajoutés.
- Middleware natif préservé, pas d'interférence SSE.
- Aucun composant UI inventé (infrastructure uniquement).
