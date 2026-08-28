# Architecture — ktutor

> Source de vérité technique : `CLAUDE.md`. Décisions structurantes : `docs/decisions/NNN-*.md`. Règles pipeline : `AGENTS.md`.
> Date : 2026-08-28. Scope : framing (la story s01 commence l'implémentation, ce doc cadre).

## Stack

### Backend
- **Langage** : Python 3.12+
- **Framework HTTP** : FastAPI 0.115+ avec Uvicorn
- **ORM** : SQLAlchemy 2.0+ + Alembic pour les migrations
- **Auth** : JWT RS256 (PyJWT + `cryptography`), bcrypt pour les mots de passe
- **Orchestration agents** : LangGraph + `langgraph-supervisor`
- **Framework agents** : LangChain 0.3+ (`langchain-core`, `langchain-openai`, `langchain-community`)
- **LLM (par défaut)** : Minimax-M3 (gratuit, suffisant pour le POC). Alternatives commuables : OpenAI GPT-4o, Mistral, Ollama. Provider sélectionné via `LLM_PROVIDER` env.
- **LLM vision** : GPT-4o ou Gemini (pour l'OCR manuscrit et l'extraction de score sur copies d'évaluation)
- **Vector Store** : ChromaDB (collection par matière × élève)
- **Embeddings** : FastEmbed (ONNX, local, gratuit) par défaut ; OpenAI en alternative
- **Document processing** : PyMuPDF (PDF), `python-docx` (DOCX), PIL (images)
- **OCR manuscrit** : LLM multimodal (GPT-4o / Gemini) avec Tesseract en fallback pour le texte imprimé
- **Task queue** : Celery + Redis (pour l'OCR, l'indexation, les extractions longues)
- **File storage** : MinIO (S3-compatible), préfixe par élève
- **Observabilité** : `loguru` (logs JSON structurés), OpenTelemetry (traces), Prometheus (`prometheus-client` pour `/metrics`)
- **Tests** : `pytest`, `httpx` pour les tests d'API

### Frontend
- **Framework** : Next.js 16 (App Router)
- **Langage** : TypeScript
- **Styling** : Tailwind CSS
- **State** : Zustand
- **API client** : Axios
- **i18n** : `next-intl` (français par défaut, anglais)
- **SSE** : `fetch` + `ReadableStream` (l'EventSource natif ne supporte pas POST)
- **Charts** : Recharts (dashboards)
- **Tests** : Playwright (e2e + a11y via `@axe-core/playwright`)

### Infrastructure
- **Conteneurisation** : Docker + `docker-compose.yml`
- **Services** : postgres, redis, minio, chroma (cf. infra)
- **Pas de Kubernetes, pas de CI/CD prod** — projet local (PRD § Hors-scope)

## Repo structure (cible)

```
ktutor/
├── backend/
│   ├── app/
│   │   ├── main.py                  # entrée FastAPI
│   │   ├── api/                     # endpoints HTTP, un sous-dossier par domaine
│   │   │   ├── auth/                #   register, login, refresh
│   │   │   ├── users/               #   create user (admin), role update, parent-child
│   │   │   ├── documents/           #   upload, list, get, delete
│   │   │   ├── chat/                #   stream, history
│   │   │   ├── exercises/           #   generate, submit
│   │   │   ├── evaluations/         #   upload, score-manual, reprocess
│   │   │   ├── dashboard/           #   eleve, parent
│   │   │   ├── notifications/       #   list, mark-as-read
│   │   │   └── metrics.py           #   /metrics Prometheus
│   │   ├── core/
│   │   │   ├── auth/                #   jwt, passwords, middleware, dependencies
│   │   │   ├── database/            #   models.py, session.py, alembic/
│   │   │   ├── config.py            #   pydantic-settings (env)
│   │   │   └── observability/       #   logging, tracing, metrics, alerts
│   │   ├── services/
│   │   │   ├── rag/                 #   ingestion, ocr, embeddings, chroma_store, retriever
│   │   │   ├── agents/              #   supervisor, maths_agent, francais_agent
│   │   │   ├── exercises/           #   qcm_generator, free_generator, flashcard_generator, qcm_grader, text_grader
│   │   │   ├── correction/          #   progressive, hints
│   │   │   ├── ocr/                 #   multimodal_ocr, evaluation_extractor
│   │   │   └── rewards/             #   ledger, levels
│   │   └── cli.py                   #   python -m ktutor.cli (utilisé par s01-s07)
│   ├── tests/                       # pytest, aligné sur la structure de app/
│   ├── scripts/                     # generate_jwt_keys.py, bootstrap_admin.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/
│   ├── app/
│   │   ├── (auth)/                  #   /login, /register
│   │   ├── (dashboard)/
│   │   │   ├── admin/
│   │   │   ├── parent/
│   │   │   └── eleve/               #   /chat, /upload, /exercises, /history, /dashboard
│   │   ├── docs/                    #   /docs/* — user guide
│   │   └── layout.tsx
│   ├── components/                  # composants UI réutilisables
│   ├── lib/
│   │   ├── api.ts                   # axios + interceptor JWT
│   │   ├── stores/                  # Zustand (auth, chat, notifications)
│   │   └── i18n.ts
│   ├── messages/                    # fr.json, en.json (next-intl)
│   ├── types/                       # types TypeScript partagés
│   ├── public/
│   ├── middleware.ts                # next-intl middleware + auth guard
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── prd.md
│   ├── stories.md
│   ├── architecture.md              # ce fichier
│   ├── roadmap.md
│   ├── decisions/                   # ADR (MADR format)
│   ├── research/                    # docs/research/<story-id>.md (sortie de /ks-research)
│   ├── plans/                       # docs/plans/<story-id>.md (sortie de /ks-plan)
│   ├── reviews/                     # docs/reviews/<story-id>.md (sortie de /ks-review)
│   └── user-guide/                  # généré par s26
├── scripts/                         # scripts transverses (bootstrap, generate-keys)
├── CLAUDE.md                        # source de vérité technique
├── AGENTS.md                        # règles pipeline killer-saas
├── README.md
└── .gitignore
```

## Patterns & conventions

### Backend (Python)

- **Endpoints FastAPI** : un sous-dossier par domaine dans `app/api/`. Chaque sous-dossier contient un `router.py` et des schémas Pydantic.
- **Services** : un sous-dossier par service dans `app/services/`. Pas de logique métier dans les routers — ils délèguent aux services.
- **Agents LangGraph** : un fichier par agent dans `app/services/agents/`. Le superviseur est un fichier à part. Les agents reçoivent le `pseudo` du JWT en paramètre explicite, jamais du state global.
- **Nommage** : snake_case pour les fichiers et fonctions, PascalCase pour les classes, kebab-case pour les URLs (`/documents/upload`, `/evaluations/score-manual`).
- **Typage** : obligatoire. Utiliser `Optional`, `List`, `Dict` du module `typing` ou les builtins PEP 604 (`list[str]`, `str | None`) en Python 3.10+. Pydantic pour les schémas d'entrée/sortie.
- **Tests** : `pytest`. Un test par AC (chaque AC devient un test). Tests d'isolation cross-tenant obligatoires pour les endpoints accédant à des données élève.
- **Logs** : `loguru` configuré pour JSON structuré. Champs : `timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`. Jamais de mot de passe, de token, ou de contenu de document dans les logs.
- **Async** : `async def` pour les endpoints et les services I/O-bound (DB, HTTP, ChromaDB). `def` sync pour le code CPU-bound ou les helpers purs.
- **Erreurs** : exceptions HTTP de FastAPI (`HTTPException`, `status.HTTP_*`). Pas de `try/except` muets — toujours logger l'exception.

### Frontend (TypeScript)

- **Structure Next.js** : App Router, routes groupées par `(auth)` et `(dashboard)`. Un dossier par route, avec `page.tsx`, `layout.tsx` (optionnel), et `loading.tsx` (optionnel).
- **Composants** : PascalCase. Un composant par fichier. Props typées avec une interface.
- **Hooks** : `useXxx`. Préférer les hooks Zustand (`useAuthStore`) aux contextes React pour le state global.
- **Stores Zustand** : un store par domaine (`authStore`, `chatStore`, `notificationsStore`). Sérialisation manuelle pour `localStorage` si persistence nécessaire.
- **API client** : `axios` avec interceptor pour ajouter le JWT (header `Authorization: Bearer <token>`) et gérer le refresh automatique sur 401.
- **i18n** : `useTranslations()` de `next-intl` dans tous les composants. Aucune string en dur. Catalogues `messages/fr.json` (par défaut) et `messages/en.json`.
- **Styling** : Tailwind classes utilitaires. Pas de CSS modules. Pas de styled-components.
- **Tests** : Playwright pour les e2e (parcours critiques : register, login, upload, chat, submit, dashboard). `@axe-core/playwright` pour l'audit a11y.
- **Accessibilité** : `<label htmlFor="...">` sur tous les champs. `aria-live="polite"` sur les zones de stream (chat, notifications). Focus visible (`:focus-visible` Tailwind). Contraste AA (4.5:1) minimum.

### Multi-tenancy (transverse)

- **PostgreSQL** : toutes les tables métier ont une colonne `student_pseudo` (FK vers `users.pseudo` ou `parent_child_links`). Toutes les requêtes filtrent par `student_pseudo` extrait du JWT (jamais du body ou de l'URL).
- **ChromaDB** : convention de nommage `rag_<subject>_<pseudo>`. Factory `get_chroma_collection(subject, pseudo)` (cf. ADR 004).
- **MinIO** : préfixe de clé `students/<pseudo>/<document_id>`. `document_id` est un UUID, pas un nom de fichier.
- **JWT** : `sub` = pseudo, `role` = "eleve" | "parent" | "admin". Middleware FastAPI vérifie le `pseudo` du JWT contre le `pseudo` de l'URL/body.
- **Tests d'isolation** : pour chaque endpoint accédant à des données élève, au moins un test vérifie qu'un élève A ne peut pas lire/écrire les données d'un élève B (JWT swap).

## Data model (résumé)

Schéma PostgreSQL (cf. stories s04, s07, s08, s12-s15, s18-s20 pour le détail complet) :

```
users (
  pseudo PK,
  password_hash,
  role ("eleve" | "parent" | "admin"),
  created_at
)

parent_child_links (
  id PK,
  parent_pseudo FK -> users.pseudo,
  child_pseudo FK -> users.pseudo,
  UNIQUE (parent_pseudo, child_pseudo)
)

documents (
  id UUID PK,
  student_pseudo FK,
  subject ("maths" | "francais"),
  filename,
  chunks_count,
  status ("indexed" | "error" | "manual_review_needed"),
  minio_key,
  created_at
)

exercises (
  id UUID PK,
  student_pseudo FK,
  subject,
  type ("qcm" | "probleme" | "redaction" | "flashcards"),
  statement TEXT,
  expected_answer TEXT,
  grading_criteria JSONB,
  generated_at
)

attempts (
  id UUID PK,
  exercise_id FK,
  student_pseudo FK,
  attempt_number,
  is_success BOOL,
  raw_answers JSONB,
  answer_text TEXT,
  correction_level ("partial" | "partial_attempt_2" | "full" | "full_after_attempts"),
  submitted_at
)

evaluations (
  id UUID PK,
  student_pseudo FK,
  subject,
  source_image_minio_key,
  extracted_score FLOAT,
  max_score FLOAT,
  annotations JSONB,
  teacher_comments TEXT,
  status ("scored" | "manual_review_needed"),
  scored_by_pseudo,           -- NULL si auto, sinon admin/parent
  created_at
)

conversations (
  id UUID PK,
  student_pseudo FK,
  subject,
  first_question TEXT,
  message_count INT,
  last_activity_at
)

messages (
  id PK,
  conversation_id FK,
  role ("user" | "assistant"),
  content TEXT,
  sources JSONB,
  created_at
)

reward_ledger (
  id PK,
  student_pseudo FK,
  amount INT,
  reason ("exercise_submit" | "bonus" | "first_try"),
  attempt_id FK NULL,
  created_at
  -- append-only, no UPDATE allowed
)

user_points (
  student_pseudo PK FK,
  total_points,
  level ("apprenti" | "confirmé" | "expert"),
  updated_at
)

notifications (
  id PK,
  student_pseudo FK,
  type ("evaluation_processed" | "points_awarded"),
  payload JSONB,
  read_at NULL,
  created_at
)
```

## Integration points

| Service | Usage | Local | Prod-ready ? |
|---|---|---|---|
| **PostgreSQL** | users, exercices, évaluations, conversations, ledger, notifications | docker-compose, port 5432 | oui (changer mot de passe, volume) |
| **Redis** | Celery broker, cache de sessions, JWT refresh blacklist | docker-compose, port 6379 | oui |
| **MinIO** | fichiers uploadés (PDFs, images) | docker-compose, port 9000 | oui (credentials) |
| **ChromaDB** | vector store par (matière × élève) | filesystem (`./chroma_data`) | non (à migrer vers Chroma server) |
| **Celery** | tâches asynchrones (OCR, indexation, extraction score) | broker = Redis | oui |
| **OpenTelemetry** | traces vers console (local) ou OTLP (env) | exporter console | oui |
| **Prometheus** | métriques sur `/metrics` | scrape via `localhost:8000/metrics` | oui |
| **LLM provider** | chat, génération exercices, OCR vision, LLM-as-judge | env `LLM_PROVIDER` (minimax | openai | mistral | ollama) | oui |
| **Embeddings** | vectorisation des chunks | FastEmbed (ONNX, local) ou OpenAI | oui |

**Hors-scope (PRD § Hors-scope)** : Stripe (paiements), PagerDuty/Slack (alerting prod), SendGrid (email), Sentry (error tracking prod), Datadog/New Relic (APM prod).

## Design / UX

- **Personas** : élève (collège 6e-3e, smartphone/tablette, usage mobile-first), parent (lecture seule, dashboard), admin (configuration).
- **Flows clés** :
  - **Élève** : register → upload document → chat avec l'agent (SSE) → générer exercice → soumettre réponse → recevoir correction progressive → voir dashboard.
  - **Parent** : admin crée le compte parent → admin lie parent à enfant → parent se connecte → parent voit la progression de l'enfant (lecture seule).
  - **Admin** : login → créer des utilisateurs → changer des rôles → voir l'ops dashboard (optionnel).
- **Screens clés** : `/login`, `/register`, `/upload`, `/chat`, `/exercises`, `/history`, `/dashboard/eleve`, `/dashboard/parent`, `/dashboard/parent/[child_pseudo]`, `/admin/users`, `/admin/ops` (optionnel).
- **Responsive** : smartphone (≥ 360px) et tablette (≥ 768px) prioritaires. Desktop secondaire.
- **A11y** : WCAG 2.1 A minimum. Lighthouse a11y ≥ 90 sur les pages principales (cf. stories s11, s22).
- **i18n** : FR par défaut, EN. Toutes les chaînes UI via `next-intl`. Pas de hardcoded strings.
- **Design system** : défini dans `/ks-design-system` (étape suivante après l'architecture). Pas de Figma, design tokens en CSS variables Tailwind.

## Observabilité

- **Logs structurés** : `loguru` configuré JSON. Chaque requête HTTP, chaque appel LLM, chaque tâche Celery émet un log avec `request_id`, `pseudo` (si auth), `route`, `duration_ms`, `status_code`.
- **Tracing** : OpenTelemetry sur FastAPI + Celery. Exporter console en local, OTLP en prod. Chaque transition de noeud LangGraph est tracée.
- **Métriques** : Prometheus sur `/metrics` (sans auth en local). Compteurs clés : `http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`, `exercises_generated_total`, `evaluations_scored_total`, `ocr_failures_total`.
- **Alerting** : règles Prometheus dans `docs/decisions/` ou `ops/prometheus/alerts.yml`. Seuils POC : taux d'erreur 5xx > 5% (2 min), p95 latency > 5s (5 min), Celery queue > 100 tâches. Affichage local en console (log ALERT) — pas de PagerDuty/Slack en POC.
- **Dashboarding** : Grafana ou simple console (à trancher par s23).

## Sécurité

- **JWT RS256** : clé privée dans `./keys/jwt_private.pem` (gitignored), clé publique dans `./keys/jwt_public.pem`. Générées par `scripts/generate_jwt_keys.py` au premier lancement.
- **Mots de passe** : bcrypt (cost factor 12). Pré-hash SHA-256 si > 72 bytes.
- **RBAC** : `Depends(get_current_user)` + `@require_role([...])` sur chaque endpoint protégé.
- **Multi-tenancy** : `pseudo` du JWT comparé au `pseudo` de l'URL/body. 403 si mismatch (sauf admin).
- **CORS** : autorisé pour `NEXT_PUBLIC_API_URL` uniquement. Pas de `*`.
- **CSP** : pas en POC (sécurité supplémentaire pour la prod).
- **Rate limiting** : pas en POC. À ajouter en prod (middleware FastAPI ou reverse proxy).
- **Scan anti-malware** : pas en POC. PRD § Notes le signale comme « phase production uniquement ».

## Décisions

Toutes les décisions structurantes sont consignées dans `docs/decisions/NNN-<slug>.md` au format MADR (cf. `templates/adr.md`). Une décision est immuable : un changement = nouvel ADR qui supersede l'ancien.

Liste actuelle :

- `001-monorepo-backend-frontend.md` — pourquoi un monorepo à deux racines
- `002-poc-rewrite-from-scratch.md` — pourquoi on réécrit le POC Python
- `003-langgraph-supervisor.md` — pourquoi LangGraph + superviseur
- `004-rag-isolation-by-collection.md` — pourquoi une collection ChromaDB par (matière × élève)
- `005-auth-rs256-rbac.md` — pourquoi JWT RS256 + RBAC trois rôles
- `006-frontend-nextjs-app-router.md` — pourquoi Next.js 16 App Router + i18n + a11y dès le départ
