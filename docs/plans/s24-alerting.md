---
validated: yes
story: s24-alerting
complexity: 2
depends_on: s23-observabilite-logs-metriques
---

# Plan s24-alerting — Alerting sur signaux critiques (POC)

## Tâches séquencées
1. [ ] Créer `alerts.py` (règles + console log `ALERT`)
2. [ ] Ajouter `celery_queue_length` dans `metrics.py`
3. [ ] Initialiser alertes dans `main.py` lifespan
4. [ ] Test synthétique 5xx (`test_alert_fires_on_5xx_storm`)
