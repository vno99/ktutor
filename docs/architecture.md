# Architecture — ktutor

> Source de vérité technique : `CLAUDE.md`. Décisions structurantes : `docs/decisions/NNN-*.md`. Règles pipeline : `AGENTS.md`.
> Date : 2026-09-02. Scope : framing (architecture cible + état réel post-s11a). Le repo est désormais bootstrapé : backend FastAPI (s01-s10) + frontend Next.js 16 (s11a shippé `c3f1829`). Ce doc cadre les patterns et la cible — l'exhaustivité par story vit dans `docs/stories.md`.

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
- **File storage** : SeaweedFS (S3-compatible), préfixe par élève
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
- **Services** : postgres, redis, seaweedfs, chroma (cf. infra)
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
│   │   │   ├── llm/                 #   client (LlmClient Protocol, ChatOpenAI factory)
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
│   │   ├── (public)/                #   pages non-protégées (pré-JWT, s11a-s11c)
│   │   │   └── [locale]/
│   │   │       ├── layout.tsx       #   <Header> + bottom tab bar (mobile)
│   │   │       ├── page.tsx         #   home (mini-hero + 2 CTAs)
│   │   │       ├── chat/page.tsx    #   s11b (à venir)
│   │   │       └── upload/page.tsx  #   s11c (à venir)
│   │   ├── (auth)/                  #   /login, /register (s12)
│   │   ├── (dashboard)/             #   pages protégées (s15+, JWT guard)
│   │   │   ├── admin/
│   │   │   ├── parent/
│   │   │   └── eleve/               #   /chat, /upload, /exercises, /history, /dashboard
│   │   ├── docs/                    #   /docs/* — user guide (s26)
│   │   ├── globals.css              #   Tailwind v4 + design tokens (CSS variables)
│   │   └── layout.tsx               #   root layout (data-theme, fonts, NextIntlClientProvider)
│   ├── components/                  # composants UI réutilisables (s11a)
│   │   ├── Button.tsx               #   primary | secondary | ghost variants
│   │   ├── Card.tsx                 #   header | body | footer
│   │   ├── FileUpload.tsx           #   drop zone (squelette s11a, complet s11c)
│   │   ├── Header.tsx               #   logo + <LanguageSwitcher> + pseudo input + avatar
│   │   ├── Input.tsx
│   │   ├── Label.tsx
│   │   ├── LanguageSwitcher.tsx     #   pill toggle FR | EN (cookie-backed)
│   │   ├── Select.tsx               #   native <select> stylé
│   │   └── StreamingMessage.tsx     #   aria-live="polite" + typing indicator
│   ├── lib/
│   │   ├── api.ts                   # axios + interceptor (JWT en s15)
│   │   ├── stores/                  # Zustand (authStore livré s11a, chatStore/uploadStore à venir)
│   │   └── i18n.ts                  # next-intl config (routing, request)
│   ├── i18n/                        # next-intl routing + request config
│   │   ├── routing.ts
│   │   └── request.ts
│   ├── messages/                    # fr.json (default), en.json
│   ├── types/                       # types TypeScript partagés (à venir)
│   ├── public/                      # assets statiques
│   ├── middleware.ts                # next-intl middleware (locale routing)
│   ├── e2e/                         # Playwright tests (s11a livré : home, pseudo, responsive)
│   ├── scripts/                     # check-i18n.sh, check-api-url.sh
│   ├── lighthouserc.json            # config Lighthouse CI
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── playwright.config.ts
│   ├── .env.example
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
- **Application FastAPI** : `app/main.py` construit `FastAPI(...)` avec un `lifespan` qui appelle `init_db()` au démarrage, monte `CORSMiddleware` (origines via `Settings.cors_allow_origins_list`), puis `include_router(...)` pour chaque sous-domaine de `app/api/`. Le superviseur est construit via la factory `app.services.agents.factory.build_subject_supervisor(settings)`, partagée avec le CLI. s09 est le premier story à introduire ce scaffolding (ADR 010).
- **Services** : un sous-dossier par service dans `app/services/`. Pas de logique métier dans les routers — ils délèguent aux services.
- **Agents LangGraph** : un fichier par agent dans `app/services/agents/`. Le superviseur est un fichier à part. Les agents reçoivent le `pseudo` du JWT en paramètre explicite, jamais du state global.
- **Supervisor pattern (s05)** : le superviseur est un **dispatcher Python typé** (`SubjectSupervisor` dans `app/services/agents/supervisor.py`), pas un `StateGraph` `langgraph`. Il expose un `Protocol SubjectAgent` avec la signature `ask(subject, pseudo, question) -> ChatResult` (one-shot, s02) et `astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]` (s09). Il route par `subject` via un `dict[str, SubjectAgent]`. Voir ADR 003 (mise à jour s05) : le `StateGraph` est reporté à l'itération « routage par contenu ». La migration est encapsulée dans `SubjectSupervisor` — les agents individuels restent intacts. Le superviseur valide aussi `subject` (D3, défense en profondeur avec la validation côté agent).
- **Streaming** : s09 expose le chat en SSE via `fastapi.responses.StreamingResponse` natif (PAS `sse-starlette`, voir ADR 010). Le format est `data: <json>\n\n` avec `ensure_ascii=False`. Le client de l'agent passe par `LlmClient.astream` (ajouté en s09 au Protocol) qui est un passthrough vers `BaseChatModel.astream`.
- **Nommage** : snake_case pour les fichiers et fonctions, PascalCase pour les classes, kebab-case pour les URLs (`/documents/upload`, `/evaluations/score-manual`).
- **Typage** : obligatoire. Utiliser `Optional`, `List`, `Dict` du module `typing` ou les builtins PEP 604 (`list[str]`, `str | None`) en Python 3.10+. Pydantic pour les schémas d'entrée/sortie.
- **Tests** : `pytest`. Un test par AC (chaque AC devient un test). Tests d'isolation cross-tenant obligatoires pour les endpoints accédant à des données élève.
- **Logs** : `loguru` configuré pour JSON structuré. Champs : `timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`. Jamais de mot de passe, de token, ou de contenu de document dans les logs.
- **Async** : `async def` pour les endpoints et les services I/O-bound (DB, HTTP, ChromaDB). `def` sync pour le code CPU-bound ou les helpers purs.
- **Erreurs** : exceptions HTTP de FastAPI (`HTTPException`, `status.HTTP_*`). Pas de `try/except` muets — toujours logger l'exception.

### Frontend (TypeScript)

- **Structure Next.js** : App Router, routes groupées par `(public)` (pré-JWT, s11a-s11c) et `(dashboard)` (authentifié, s15+). L'ADR 006 prévoyait `(auth)/` et `(dashboard)/` ; la recherche s11 (Q3) a tranché pour `(public)/` car `(auth)/` en Next.js désigne sémantiquement les pages login/register (qui arrivent en s12), pas les pages non-protégées. La convention finale est : `(public)/[locale]/` = pages accessibles sans JWT (header sticky, language switcher, pseudo input), `(dashboard)/[locale]/` = pages protégées (gated par middleware en s15+). Un dossier par route, avec `page.tsx`, `layout.tsx` (optionnel), `loading.tsx` (optionnel).
- **Composants** : PascalCase. Un composant par fichier. Props typées avec une interface.
- **Hooks** : `useXxx`. Préférer les hooks Zustand (`useAuthStore`) aux contextes React pour le state global.
- **Stores Zustand** : un store par domaine (`authStore`, `chatStore`, `notificationsStore`). Sérialisation manuelle pour `localStorage` si persistence nécessaire.
- **API client** : `axios` avec interceptor pour ajouter le JWT (header `Authorization: Bearer <token>`) et gérer le refresh automatique sur 401. Pré-JWT (s11a-s11c), le client ne fait pas d'auth ; le `pseudo` est envoyé dans le `body` des endpoints conformément aux contrats s09 (`/api/chat/stream`) et s10 (`/api/documents/upload`). Le passage JWT s15 remplace le `body.pseudo` par le header `Authorization` (refacto encapsulée dans les stores `chatStore` / `uploadStore` / `authStore`).
- **Stores Zustand et hydratation** : un store par domaine (`authStore`, `chatStore`, `notificationsStore`, `uploadStore`). Hydratation **client-side only** via `hydrate()` appelé après mount (`useEffect` dans le root layout). Pas de SSR state Zustand (limitation Next.js 16 App Router). `authStore` porte depuis s13 `accessToken` + `refreshToken` + `role` en plus de `pseudo` ; la source de vérité canonique côté backend est le `sub` du JWT, le `pseudo` cookie n'est qu'un cache de transition (ADR 011). `chatStore` / `uploadStore` parsent les réponses streaming ou multipart. Les stores ne sont **pas** des singletons globaux Next.js (ils sont par-requête), ce qui est compatible avec le RSC et le multi-tenant.
- **i18n** : `useTranslations()` de `next-intl` dans tous les composants. Aucune string en dur. Catalogues `messages/fr.json` (par défaut) et `messages/en.json`.
- **Styling** : Tailwind classes utilitaires. Pas de CSS modules. Pas de styled-components.
- **Tests** : Playwright pour les e2e (parcours critiques : register, login, upload, chat, submit, dashboard). `@axe-core/playwright` pour l'audit a11y.
- **Accessibilité** : `<label htmlFor="...">` sur tous les champs. `aria-live="polite"` sur les zones de stream (chat, notifications). Focus visible (`:focus-visible` Tailwind). Contraste AA (4.5:1) minimum.

### Multi-tenancy (transverse)

- **PostgreSQL** : toutes les tables métier ont une colonne `student_pseudo` (FK vers `users.pseudo` ou `parent_child_links`). Toutes les requêtes filtrent par `student_pseudo` extrait du JWT (jamais du body ou de l'URL).
- **ChromaDB** : convention de nommage `rag_<subject>_<pseudo>`. Factory `get_chroma_collection(subject, pseudo)` (cf. ADR 004).
- **SeaweedFS (S3)** : préfixe de clé `students/<pseudo>/<document_id>`. `document_id` est un UUID, pas un nom de fichier. Le SDK Python `minio>=7.2` (compatible S3) est utilisé.
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
  s3_key,
  created_at
)

exercises (
  id UUID PK,
  student_pseudo FK,
  subject,
  type ("qcm" | "probleme" | "redaction" | "flashcards"),  -- s03 wired QCM only
  document_id UUID FK -> documents.id,
  statement TEXT,                     -- nullable; QCM leaves it null
  expected_answer TEXT,               -- nullable; QCM leaves it null
  grading_criteria JSON,              -- nullable; QCM leaves it null
  questions JSON,                     -- QCM payload: [{question, options[4], correct_index}]
  created_at                          -- "created_at" (not "generated_at") to match Document
)

-- Note: ``exercises.questions`` is stored as ``sqlalchemy.JSON`` (portable
-- SQLite/Postgres) rather than ``JSONB`` so the test suite can run on
-- SQLite in-memory. The schema above is the current ORM definition; an
-- Alembic migration is deferred to s15 (consolidates ``exercises`` with
-- the ``users`` FK). ``init_db()`` keeps the table in sync in dev/CI.

attempts (
  id UUID PK,
  exercise_id FK,
  student_pseudo FK,
  attempt_number,                       -- per (pseudo, exercise_id), 1-based, via MAX
  is_success BOOL,
  raw_answers JSON,                     -- list[int], one per QCM question
  answer_text TEXT,                     -- nullable; QCM leaves it null (s07)
  correction_level ("partial" | "partial_attempt_2" | "full" | "full_after_attempts"),
                                        -- nullable; QCM leaves it null (s08)
  submitted_at
)

-- Note: ``attempts`` is created by s04. ``raw_answers`` is stored as
-- ``sqlalchemy.JSON`` (portable SQLite/Postgres), not ``JSONB``, so the
-- test suite can run on SQLite in-memory. ``answer_text`` and
-- ``correction_level`` are pre-created nullable so the schema is stable
-- for s07 (rédaction) and s08 (correction progressive) without an Alembic
-- migration at every story boundary. The FKs to ``users.pseudo`` and
-- ``exercises.id`` are deferred to s15 (the consolidation migration).
-- ``init_db()`` applies the full ``Base`` metadata in dev/CI.

evaluations (
  id UUID PK,
  student_pseudo FK,
  subject,
  source_image_s3_key,
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

## API Endpoints

### Documents — `backend/app/api/documents/` (s10)

| Endpoint | Method | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `/api/documents/upload` | POST | `multipart/form-data` — `pseudo: str`, `subject: Literal["maths","francais"]`, `file: UploadFile` | `201 {document_id, status, chunks_count, ocr_confidence?}` | `413` (taille), `415` (extension), `422` (pseudo / OCR), `500` (S3/DB) |

**Request fields** :

* `pseudo` — auth-stub identity (regex `^[a-zA-Z0-9_]{3,32}$` enforced
  in the service). Migration JWT en s15.
* `subject` — `Literal["maths", "francais"]` (Pydantic validation côté
  router).
* `file` — `UploadFile` (PDF, PNG, JPG, JPEG, TXT). Limite
  `max_upload_size_mb` (défaut 20 MB), contrôlée à trois niveaux :
  header `Content-Length` → post-read router → `UploadService.upload`.

**Réponse succès** :

```json
{
  "document_id": "uuid",
  "status": "indexed" | "manual_review_needed" | "error",
  "chunks_count": 0,
  "ocr_confidence": 0.9
}
```

`MANUAL_REVIEW_NEEDED` est un succès HTTP 201 — le document est
persisté en base avec `chunks_count=0` (OCR confidence trop basse,
Piège 7). Le frontend décide de l'affichage.

**Erreurs** :

| Code | Status | Quand |
| --- | --- | --- |
| `invalid_pseudo` | 422 | `pseudo` ne matche pas la regex |
| `invalid_file` | 413 | fichier > `max_upload_size_mb` (taille) |
| `invalid_file` | 415 | extension non supportée |
| `ocr_failure` | 422 | échec OCR (HTTP 5xx upstream) |
| `storage_failure` | 500 | S3 ou DB injoignable |

**Architecture** : le router (`app/api/documents/router.py`) appelle
directement `UploadService.upload(file_path, pseudo, subject)` (AC4).
Le service est la **même fonction** que le CLI invoque
(`app/cli.py:333` — `python -m ktutor.cli upload`). Aucune logique
métier dans le router. CORS hérité de s09 (`CORSMiddleware` dans
`app/main.py`, configuré via `Settings.cors_allow_origins`).

## Integration points

| Service | Usage | Local | Prod-ready ? |
|---|---|---|---|
| **PostgreSQL** | users, exercices, évaluations, conversations, ledger, notifications | docker-compose, port 5432 | oui (changer mot de passe, volume) |
| **Redis** | Celery broker, cache de sessions, JWT refresh blacklist | docker-compose, port 6379 | oui |
| **SeaweedFS (S3)** | fichiers uploadés (PDFs, images) | docker-compose, port 8333 | oui (credentials) |
| **ChromaDB** | vector store par (matière × élève) | filesystem (`./chroma_data`) | non (à migrer vers Chroma server) |
| **Celery** | tâches asynchrones (OCR, indexation, extraction score) | broker = Redis | oui |
| **OpenTelemetry** | traces vers console (local) ou OTLP (env) | exporter console | oui |
| **Prometheus** | métriques sur `/metrics` | scrape via `localhost:8000/metrics` | oui |
| **LLM provider** | chat, génération exercices, OCR vision, LLM-as-judge | env `LLM_PROVIDER` (minimax | openai | mistral | ollama). `minimax` est routé via OpenRouter (`LLM_BASE_URL` = `https://openrouter.ai/api/v1`) avec `ChatOpenAI`. | oui |
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
- `007-minio-from-s01.md` — pourquoi MinIO (objet storage) pour les fichiers uploadés
- `008-deepseek-ocr-2-for-vision.md` — pourquoi DeepSeek-OCR-2 pour la vision LLM
- `009-seaweedfs-replaces-minio.md` — pourquoi SeaweedFS remplace MinIO en local
- `010-fastapi-streaming.md` — pourquoi `StreamingResponse` natif + `LlmClient.astream` + `pseudo` dans le body (s09)
