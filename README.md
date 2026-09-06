# ktutor — Assistant pédagogique multi-agents

Assistant de devoir intelligent pour collégiens, basé sur une architecture multi-agents avec LangGraph. L'élève uploade ses cours, pose des questions à un chatbot RAG, génère des exercices personnalisés, et reçoit une **correction progressive** de ses réponses.

**Fonctionnement :** l'élève soumet sa réponse à un exercice. Si le score est insuffisant, seuls des indices sont dévoilés. Après 3 tentatives infructueuses, la correction complète est révélée.

> Version : projet local en développement. Stack complète (frontend + backend + agents IA) fonctionnelle.

---

## Table des matières

- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Structure du projet](#structure-du-projet)
- [Fonctionnalités clés](#fonctionnalités-clés)
- [API](#api)
- [Développement](#développement)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Next.js 16)             │
│         Responsive (360px+) / i18n FR+EN            │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│                 Backend (FastAPI)                     │
│  ┌──────────────────────────────────────────────┐   │
│  │        LangGraph Superviseur                  │   │
│  │        (aiguillage vers agent matière)        │   │
│  └──────────────────────────────────────────────┘   │
│         │                    │                      │
│  ┌──────▼──────┐    ┌──────▼──────┐                │
│  │ Agent Maths  │    │ Agent Francais│               │
│  │ + RAG       │    │ + RAG        │               │
│  └─────────────┘    └──────────────┘                │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
    │ChromaDB │  │PostgreSQL│  │SeaweedFS │
    │(vectors)│  │   (BD)   │  │  (S3)   │
    └─────────┘  └──────────┘  └─────────┘
```

**Multi-tenancy** : chaque élève a son propre RAG (`rag_<matiere>_<pseudo>`), ses propres documents, et son propre historique. L'isolation est garantie par le `pseudo` du JWT.

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS, Zustand, next-intl |
| Backend | FastAPI (Python), SQLAlchemy + Alembic, Celery + Redis |
| IA | LangGraph + LangChain, Minimax-M3 (défaut), ChromaDB |
| Vision | LLM multimodal (GPT-4o / Gemini) pour OCR manuscrit |
| Base de données | PostgreSQL 16 |
| Stockage fichiers | SeaweedFS (S3-compatible) |
| Vector store | ChromaDB |
| Conteneurisation | Docker + docker-compose |

---

## Démarrage rapide

### Prérequis

- Docker + docker-compose
- Node.js 20+
- Python 3.11+
- pnpm

### 1. Cloner et configurer

```bash
git clone https://github.com/vno99/ktutor.git
cd ktutor
cp .env.example .env
```

### 2. Lancer les services (Docker)

```bash
docker-compose up -d
# Vérifie que les services sont prêts
docker-compose ps
```

Attendre que PostgreSQL, Redis, SeaweedFS et ChromaDB soient healthy (`healthy` dans la colonne `STATUS`).

### 3. Backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head   # applique les migrations DB
uvicorn app.main:app --reload --port 8000
```

Le backend écoute sur `http://localhost:8000`. La documentation Swagger est sur `http://localhost:8000/docs`.

### 4. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Le frontend écoute sur `http://localhost:3000`. L'application redirige automatiquement vers `/fr/` (locale par défaut).

### 5. (Optionnel) Worker Celery

```bash
cd backend
celery -A app.services.tasks worker --loglevel=info
```

---

## Structure du projet

```
ktutor/
├── backend/
│   ├── app/
│   │   ├── api/              # Routes FastAPI
│   │   │   ├── auth/         # Register, login, refresh, logout
│   │   │   ├── chat/         # /api/chat/stream (SSE)
│   │   │   ├── documents/     # /api/documents/upload
│   │   │   ├── exercises/    # /api/exercises/generate, /submit
│   │   │   ├── evaluations/   # /api/evaluations/upload
│   │   │   ├── users/        # CRUD + parent-child links
│   │   │   └── dashboard/     # /api/dashboard/eleve, /parent
│   │   ├── core/             # Auth (JWT RS256), database, config
│   │   └── services/          # Logique métier
│   │       ├── agents/       # LangGraph agents (maths, francais)
│   │       ├── rag/           # Ingestion, chunking, embeddings
│   │       ├── ocr/           # OCR manuscrit
│   │       └── correction/    # Correction progressive
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── (auth)/           # Login, register
│   │   ├── (dashboard)/       # Pages protégées
│   │   │   ├── admin/
│   │   │   ├── parent/
│   │   │   └── eleve/
│   │   └── (public)/[locale]/ # Routes publiques (i18n)
│   │       ├── page.tsx       # Home
│   │       ├── chat/
│   │       ├── upload/
│   │       └── docs/          # Guide utilisateur
│   ├── components/            # Design system (Button, Card, etc.)
│   ├── lib/                  # Zustand stores, Axios config
│   ├── messages/              # Catalogues i18n (fr.json, en.json)
│   └── e2e/                  # Tests Playwright
├── docs/
│   ├── user-guide/           # Guide utilisateur (eleve, parent, admin)
│   ├── stories.md             # Product backlog (stories)
│   ├── architecture.md        # Décisions architecturales
│   └── design-system.md      # Design tokens, composants
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Fonctionnalités clés

### Chat RAG par matière

L'élève pose une question en langage naturel. Le superviseur LangGraph aiguille vers l'agent de la matière concernée (Maths ou Français). L'agent récupère les chunks pertinents dans ChromaDB et génère une réponse sourcée.

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"pseudo": "alice", "subject": "maths", "question": "Comment calculer une dérivée ?"}'
# Réponse en streaming SSE
```

### Génération d'exercices

Quatre types d'exercices : **QCM**, **problème**, **rédaction**, **flashcards**. Le LLM génère l'énoncé à partir des documents uploadés par l'élève.

```bash
curl -X POST http://localhost:8000/api/exercises/generate \
  -H "Content-Type: application/json" \
  -d '{"pseudo": "alice", "subject": "maths", "type": "qcm", "difficulty": "facile"}'
```

### Correction progressive

1. L'élève soumet sa réponse (texte ou photo manuscrite).
2. Le système évalue : QCM (tout-ou-rien), rédaction (appréciation LLM).
3. **Score ≥ 80%** → correction complète dévoilée.
4. **Score < 80%** → indices uniquement. L'élève peut re-tenter (max 3).
5. Après 3 tentatives → correction complète.

```bash
curl -X POST http://localhost:8000/api/exercises/submit \
  -H "Content-Type: application/json" \
  -d '{"exercise_id": "...", "answer": "Ma réponse..."}'
```

### Extraction de scores sur évaluations

L'élève upload une copie d'évaluation corrigée par l'enseignant (photo ou PDF). Le LLM multimodal extrait automatiquement le score, les annotations et les commentaires.

```bash
curl -X POST http://localhost:8000/api/evaluations/upload \
  -F "file=@copie.jpg" \
  -F "pseudo=alice" \
  -F "subject=maths"
```

### Système de récompenses

- **5 points** par soumission d'exercice.
- **+2 points bonus** si réussite du premier coup.
- Niveaux : Apprenti → Confirmé → Expert.

### Dashboards

- **Élève** : scores par matière, historique des exercices, récompenses.
- **Parent** : vue lecture seule sur la progression de chaque enfant lié.

---

## API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/auth/register` | Créer un compte élève |
| POST | `/api/auth/login` | Connexion → JWT |
| POST | `/api/auth/refresh` | Rafraîchir le token |
| POST | `/api/chat/stream` | Chat RAG (SSE) |
| POST | `/api/documents/upload` | Uploader un document |
| POST | `/api/exercises/generate` | Générer un exercice |
| POST | `/api/exercises/submit` | Soumettre une réponse |
| POST | `/api/evaluations/upload` | Uploader une évaluation |
| GET | `/api/dashboard/eleve` | Dashboard élève |
| GET | `/api/dashboard/parent` | Dashboard parent |

Toutes les routes authentifiées (sauf register/login) requieren un JWT `Authorization: Bearer <token>`.

---

## Développement

### Tests

```bash
# Backend
cd backend && pytest

# Frontend (Playwright)
cd frontend && pnpm exec playwright test

# Les deux
docker-compose up -d backend-tests && pytest
```

### Ajouter une nouvelle langue

1. Ajouter la locale dans `frontend/i18n/routing.ts` (`locales`)
2. Créer `frontend/messages/<locale>.json` (copie de `fr.json` à traduire)
3. Ajouter les routes traduites dans `frontend/app/(public)/[locale]/`

### Variables d'environnement

Voir `.env.example` pour la liste complète. Les variables importantes :

- `DATABASE_URL` — connexion PostgreSQL
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` — durée du token d'accès (30 min par défaut)
- `LLM_PROVIDER` — `minimax` (défaut), `openai`, `ollama`
- `MINIMAX_API_KEY`, `OPENAI_API_KEY` — clés API des providers
- `MAX_CORRECTION_ATTEMPTS` — nombre de tentatives avant correction complète (3)

---

## Équipe et license

Projet développé dans le cadre du portfolio.

Les données utilisateurs sont des **pseudos** uniquement — aucune donnée personnelle n'est collectée (projet local, hors scope RGPD/CNIL).
