# Stories candidates — ktutor

> Généré par `/ks-init` le 2026-08-27. À affiner via `/ks-stories` (chaque story sera éclatée, numérotée `sNN-<slug>`, et déplacée vers son cycle Research → Plan → Execute).

## Phase 1 — POC (Maths)

Cible : un élève de collège upload un PDF ou une image (dactylographiée OU manuscrite), pose une question, génère un QCM, et obtient une réponse cohérente issue de ses documents.

- [ ] **STORY-001** : Pipeline RAG (PDF/image → OCR si besoin → Chunks → ChromaDB)
- [ ] **STORY-002** : Agent unique Maths avec LangChain + RAG
- [ ] **STORY-003** : Test LLM multimodal sur écriture manuscrite (échantillon de copies réelles)
- [ ] **STORY-004** : Script Python fonctionnel de bout en bout (CLI)
- [ ] **STORY-005** : Initialisation monorepo (frontend/ + backend/ + docker-compose Postgres/Redis/MinIO/Chroma)
- [ ] **STORY-006** : Configuration LLM Minimax-M3 (provider, client, .env, tests de connexion)
- [ ] **STORY-007** : Génération de QCM à partir d'un document (1 matière, 1 difficulté)

## Phase 2 — MVP (Maths → Français + API + Frontend)

- [ ] **STORY-008** : API FastAPI `/chat` (streaming SSE)
- [ ] **STORY-009** : API FastAPI `/documents/upload` (multipart, multi-format)
- [ ] **STORY-010** : Frontend minimal (chat + upload, responsive)
- [ ] **STORY-011** : Agent Français + scoring rédaction (appréciation LLM)
- [ ] **STORY-012** : Isolation multi-tenant (student_pseudo dans RAG + API + tests d'isolation)
- [ ] **STORY-013** : Génération d'exercices problèmes (maths collège) + correction LLM
- [ ] **STORY-014** : Génération de flashcards (maths + français)

## Phase 3 — Rôles et Sécurité

- [ ] **STORY-015** : Authentification JWT (RS256, pseudo, login/logout/refresh)
- [ ] **STORY-016** : Modèles PostgreSQL Users / Roles / parent-child link
- [ ] **STORY-017** : Middleware RBAC (admin / parent / élève)
- [ ] **STORY-018** : Dashboard parent (lecture seule sur ses enfants)

## Phase 4 — Pédagogie

- [ ] **STORY-019** : Correction progressive end-to-end (soumission + dévoilement + 3 tentatives)
- [ ] **STORY-020** : Évaluation : upload copie corrigée + extraction score (LLM multimodal)
- [ ] **STORY-021** : Dashboards élève (scores, exercices tentés, progression par matière)
- [ ] **STORY-022** : Historique des conversations (chat)
- [ ] **STORY-023** : Système de récompenses (points, paliers, historique)

## Phase 5 — Finalisation

- [ ] **STORY-024** : i18n (next-intl FR/EN, backend Accept-Language)
- [ ] **STORY-025** : Observabilité (logs structurés, OTel, Prometheus, alerting)
- [ ] **STORY-026** : Accessibilité (WCAG 2.1 A, tests Lighthouse)
- [ ] **STORY-027** : Notifications in-app
- [ ] **STORY-028** : Tests + documentation utilisateur

## Notes

- Le Français démarre en **phase 2 starter** (cf. `docs/prd.md` § Séquentialité POC).
- Les stories sont indicatives. L'agent `/ks-stories` les affinera, les numérotera (`s01-…`), et n'en gardera qu'un sous-ensemble par cycle.
- Toute story qui touche à des données élève doit inclure un **test d'isolation multi-tenant** (cf. `CLAUDE.md` § Multi-tenancy).
- Toute story qui ajoute du code doit respecter les conventions d'**observabilité** (cf. `CLAUDE.md` § Observabilité) et d'**i18n** (cf. `CLAUDE.md` § Internationalisation).
