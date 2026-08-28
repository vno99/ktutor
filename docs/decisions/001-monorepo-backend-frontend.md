# ADR 001 — Monorepo backend (FastAPI) + frontend (Next.js)

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le PRD (`docs/prd.md`) impose une stack hétérogène : un backend Python (FastAPI + LangGraph + ChromaDB + PostgreSQL + Celery) et un frontend TypeScript (Next.js 16). Ces deux artefacts ont des cycles de release différents, des toolchains différentes (pip vs npm), des équipes/types de contributeurs différents, mais partagent le domaine métier (mêmes modèles, mêmes contrats d'API, mêmes variables d'environnement).

La question est : comment organiser le dépôt pour que les deux coexistent sans se marcher dessus, tout en gardant une source de vérité unique pour la spec ?

## Decision

Adopter un **monorepo à deux racines** :

```
ktutor/
├── backend/         # FastAPI, LangGraph, ChromaDB, Celery
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/        # Next.js 16, Zustand, next-intl
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── messages/
│   ├── package.json
│   └── next.config.js
├── docker-compose.yml   # postgres, redis, minio, chroma, backend, frontend
├── docs/                # PRD, stories, architecture, ADR, reviews
├── CLAUDE.md            # source de vérité technique
└── AGENTS.md            # règles pipeline killer-saas
```

Pas de pnpm workspace / turborepo : la frontière entre `backend/` et `frontend/` est trop dure (langages, deps) pour qu'un bundler monorepo apporte un gain net. Un `Makefile` ou un script shell au top-level orchestre les commandes dev/test.

Le POC Python existant (`src/`, `test_quick.py`) est **réécrit** (cf. ADR 002) et n'est pas migré tel quel.

## Considered options

- **Polyrepo (backend/ et frontend/ dans deux dépôts Git séparés)** — rejeté parce que la spec (`CLAUDE.md`, `docs/`) doit rester synchronisée entre les deux dépôts. Le risque de drift est élevé pour un projet mono-équipe en local. Un monorepo simplifie la traçabilité des changements transversaux (un commit qui modifie un contrat d'API peut toucher les deux côtés).

- **Monorepo avec pnpm/turborepo workspaces** — rejeté parce que le backend est Python (pas de node workspaces). Pour relier les deux il faudrait Poetry + un système de workspace exotique, sans gain clair par rapport à deux racines simples.

- **Tout-en-un (Next.js API routes + logique Python embarquée via Pyodide)** — rejeté : absurdité technique pour un projet qui a besoin de Celery, ChromaDB natif, et LLM streaming côté serveur.

## Consequences

- **Plus simple** : un seul `git clone`, un seul PR, un seul CI (si jamais on en met un).
- **Plus risqué côté couplage** : rien n'empêche le frontend d'importer un module Python (il ne le fera pas, mais la tentation existe). Le respect de la frontière est documentaire, pas technique. Compensé par les conventions dans `AGENTS.md` § Technical conventions.
- **Pas de partage de code type-safe** entre backend et frontend. Les contrats d'API sont documentés dans `CLAUDE.md` § APIs et Endpoints et exportés en Pydantic côté backend, OpenAPI généré. Côté frontend, on regénère les types (ou on les écrit à la main pour le POC).
- **Docker compose orchestre tout** : `docker-compose up` lance postgres, redis, minio, chroma, backend, frontend. Le dev local peut aussi tourner en hybride (Postgres dans Docker, backend en `uvicorn` local, frontend en `npm run dev`).
