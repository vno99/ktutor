# Design — Story s23-observabilite-logs-metriques

## Screen(s)
Aucun écran utilisateur pour s23 — cette story est pure infrastructure backend (observabilité). Il n'y a pas de page frontend, pas de nouveau composant UI, pas de mockup visuel à produire.

Le travail se fait dans le code :
- `backend/app/core/logging.py` (extension du payload JSON)
- `backend/app/core/observability/` (nouveau dossier : log, trace, metrics, alerts)
- `backend/app/main.py` (middleware HTTP + OTEL dans lifespan)
- `backend/app/api/metrics.py` (nouveau endpoint `/metrics`)
- `backend/app/services/llm/client.py` (wrapper log LLM)
- `backend/app/services/agents/supervisor.py` (traces OTEL)
- `requirements.txt` et `.env` (packages + variables)

## Mockup
Le `.html` (`docs/designs/s23-observabilite-logs-metriques.html`) existe comme document de référence technique (pas un écran utilisateur) — il montre la structure du pipeline d'observabilité (middleware → loguru → OTEL → Prometheus) sans utiliser de tokens ou composants UI du design system.

Pour référence, la structure technique du système d'observabilité (pas une UI) :

```
┌─────────────────────────────┐
│  FastAPI Middleware         │  ← log chaque requête HTTP (duration, request_id, pseudo)
│  (main.py)                  │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│  Loguru (JSON)              │  ← timestamp, level, message, extra (request_id, pseudo, route, duration_ms)
│  (core/logging.py)          │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│  OpenTelemetry Traces       │  ← console (local) / OTLP (env=otlp)
│  (core/observability/)      │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│  Prometheus /metrics        │  ← endpoint sans auth (local)
│  (api/metrics.py)           │
└─────────────────────────────┘
```

## Reused components (from the design system)
Aucun composant UI réutilisé — pas d'écran. Les éléments techniques réutilisent uniquement le code backend existant (`Button`, `Card`, `StreamingMessage` ne sont pas concernés).

## States
Pas d'états UI. Les états du système d'observabilité sont :
- `actif` — middleware monté, OTEL exporte, `/metrics` répond
- `partiellement actif` — middleware monté mais OTEL ou metrics non encore configurés (état intermédiaire pendant la mise en place)
- `inactif` — rien de monté (état actuel du repo)

## Design system gaps
Aucun gap du design system visuel — s23 ne touche pas au UI. Cependant, deux besoins non couverts par le système actuel apparaissent et doivent être notés (non inventés) :
- **Pas de composant `<MetricsViewer>`** ou `<ObservabilityPanel>` dans le design system — si une future story (ex. admin ops dashboard) demande un écran de visualisation des métriques, un nouveau composant devra être ajouté au design system.
- **Pas de `<LogStream>`** ou composant d'affichage de logs — même logique : à créer lors d'une future story UI d'observabilité.

Le design system actuel (`docs/design-system.md`) n'a pas de token ni composant spécifique à l'observabilité (pas de couleur `info`, pas d'icône `activity`, pas de composant `StatusIndicator`). Cela est cohérent : ces éléments ne sont pas nécessaires pour s23 (pas d'écran utilisateur), mais le gap doit être documenté pour éviter d'inventer un token non existant lors d'une future story UI.
