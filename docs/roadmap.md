# Roadmap — ktutor

> Reprise des phases du `CLAUDE.md`. Le calendrier est purement informatif (projet local, pas de date butoir).
> Cible : **collégiens** (6e-3e), matières **Maths** puis **Français**.

## Phase 1 — POC Maths

**Objectif** : valider la chaîne RAG + agent + génération d'exercices sur la matière Maths uniquement.

**Périmètre** :

- Pipeline RAG (PDF, image dactylo, image manuscrite via OCR multimodal).
- 1 agent Maths (LangChain + ChromaDB).
- Génération de QCM.
- Script CLI de bout en bout (preuve de concept).

**Critère de succès** :
Un élève de collège uploade un document (PDF ou image dactylo OU manuscrite), génère un QCM, pose une question, et reçoit une réponse correcte et sourcée issue du document.

**Hors-phase-1** : le Français, l'API, le frontend, l'authentification, les dashboards.

## Phase 2 — MVP (Maths complet + démarrage Français)

**Objectif** : ouvrir le produit à un usage interactif via API + frontend, et démarrer le Français.

**Périmètre** :

- API FastAPI (chat streaming SSE + upload documents).
- Frontend minimal (Next.js 16, responsive smartphone/tablette).
- Agent Français (scoring rédaction par appréciation LLM).
- Isolation multi-tenant (student_pseudo dans RAG + API + tests cross-tenant).
- Génération problèmes (maths) + flashcards (maths + français).

**Critère de succès** : un élève (sans auth formelle encore) peut uploader, chatter, générer et résoudre un exercice maths OU français via le frontend.

## Phase 3 — Rôles et Sécurité

**Objectif** : ajouter l'authentification et le RBAC pour ouvrir à plusieurs utilisateurs.

**Périmètre** :

- JWT RS256 (login, refresh, logout).
- PostgreSQL : Users, Roles, parent-child links.
- Middleware RBAC (admin / parent / élève).
- Dashboard parent (lecture seule).

**Critère de succès** : un parent peut s'inscrire, lier son enfant, et consulter la progression de l'enfant sans pouvoir modifier.

## Phase 4 — Pédagogie

**Objectif** : activer le cœur pédagogique — correction progressive et évaluations.

**Périmètre** :

- Correction progressive end-to-end (QCM tout-ou-rien + rédaction par appréciation + 3 tentatives max).
- Upload de copies d'évaluation + extraction score (LLM multimodal).
- Dashboards élève (scores, exercices tentés, progression par matière).
- Historique des conversations.
- Système de récompenses (points, paliers).

**Critère de succès** : un élève soumet un exercice, le système évalue, dévoile les indices puis la correction complète après 3 échecs. Les parents voient l'évolution.

## Phase 5 — Finalisation

**Objectif** : rendre le produit présentable et maintenable.

**Périmètre** :

- i18n (next-intl FR/EN, header Accept-Language côté backend).
- Observabilité (logs structurés, OpenTelemetry, Prometheus, alerting).
- Accessibilité (WCAG 2.1 A, tests Lighthouse ≥ 90).
- Notifications in-app.
- Tests + documentation utilisateur.

**Critère de succès** : Lighthouse Accessibility ≥ 90, logs JSON parsables, alertes actives sur les seuils définis.

## Notes

- Le découpage en storiesshippables se fait via `/ks-stories`.
- Chaque story = un cycle Research → Plan → Execute → Review → Ship.
- Voir `AGENTS.md` pour les règles de pipeline (worktree, gate, ship).
- Toute story qui touche à des données élève doit inclure un test d'isolation multi-tenant.
- Le Français démarre en **starter de phase 2** (cf. `docs/prd.md` § Séquentialité POC).
