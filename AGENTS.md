# ktutor — Repo rules

## Règle absolue

Pas de code en direct. Chaque fonctionnalité passe par le pipeline suivant, dans l'ordre :

**PRD → User Stories → Architecture → par story : Research → Plan → Execute → Review → Ship**

Le `CLAUDE.md` à la racine est la **source de vérité technique** du projet. Tout agent qui démarre une tâche doit d'abord **lire le `CLAUDE.md` complet** avant toute autre action. Le pipeline s'appuie sur ses conventions :

- **Stack** : Next.js 16, FastAPI, LangGraph, ChromaDB, PostgreSQL, SeaweedFS (S3-compatible, cf. ADR 009), Celery/Redis
- **Architecture** : superviseur + agents spécialisés + RAG par matière
- **Multi-tenancy** : isolation stricte par élève (puis par matière)
- **Correction progressive** : QCM = tout ou rien, rédaction = appréciation LLM
- **RBAC** : admin / parent / élève
- **Observabilité** : logs structurés, tracing OTel, métriques Prometheus, alerting
- **i18n** : next-intl, français par défaut, anglais
- **Accessibilité** : responsive smartphone/tablette, WCAG 2.1 niveau A
- **LLM par défaut** : Minimax-M3 (gratuit, local)
- **Identité** : pseudo uniquement, pas de données personnelles

Aucun code n'est écrit avant qu'un plan validé existe (`docs/plans/<id>.md` avec `validated: yes`). Aucune fonctionnalité n'est livrée sans review passée (`docs/reviews/<id>.md` avec `Ship allowed: yes`).

## Mode Quick Fix — exception au pipeline

Le **Quick Fix** est l'exception explicite pour un ajustement petit, local, bien compris et facilement réversible. Il s'applique uniquement quand l'utilisateur le demande explicitement. L'agent principal l'implémente directement, sans pipeline complet ni TDD obligatoire. Pas de délégation d'implémentation à un sous-agent (un sous-agent peut faire de l'investigation read-only ou une review optionnelle).

Exemples typiques : changer une couleur, corriger un libellé court, ajuster un espacement responsive, restaurer un afford existant, modifier une chaîne i18n.

Le Quick Fix **ne s'applique pas** à : nouvelle feature, redesign de composant partagé, modèle de données, migration, changement d'API ou de contrat, autorisation, sécurité, règles métier, persistance, refactor transverse, changement de dépendance, modification d'un endpoint RAG ou de l'isolation multi-tenant. Si le Quick Fix s'avère trop large, l'agent principal l'arrête, recommande le pipeline normal, et ne continue pas.

L'agent principal doit annoncer le mode Quick Fix et son scope exact avant d'éditer, garder le diff minimal, préserver les abstractions existantes, et faire une vérification proportionnée (lint, typecheck, test ciblé ou vérif visuelle).

## Pipeline (commandes)

- `/ks-prd`         — cadre le périmètre (QUOI + POURQUOI). Lit `CLAUDE.md` d'abord.
- `/ks-stories`     — découpe en user stories shippables
- `/ks-architect`   — fige le HOW technique et les conventions (renforce `CLAUDE.md` si besoin)
- `/ks-research`    — explore le contexte réel de la story (code existant, APIs, pièges)
- `/ks-plan`        — découpe la story en tâches séquencées
- `/ks-execute`     — implémente la story en TDD
- `/ks-review`      — review anti-hallucination + gate
- `/ks-ship`        — ouvre la PR ; merge manuel par défaut

Utilitaires :

- `/ks-status`      — dérive l'état du pipeline depuis les fichiers
- `/ks-help`        — aide-mémoire du pipeline (français, user-facing)

Une feature = un cycle Research → Plan → Execute → Review → Ship = une branche = une PR.

## Où le code est écrit

Deux modes. Un score de complexité ne choisit jamais le répertoire.

| Mode | Répertoire | Branche |
| --- | --- | --- |
| Quick Fix explicite | Répertoire de base du repo | `dev` ; si autre branche, stop et demande |
| Feature / story | Worktree dédié `.worktrees/<story-id>/` | `feature/<story-id>` |

Toute modification qui n'est pas un Quick Fix est une feature et utilise son worktree dédié. Jamais de branche de feature créée dans le répertoire de base.

Le sous-agent `worktree-manager` crée/vérifie le worktree avant Research. Il importe les `.env*` non trackés et installe les dépendances. Avant chaque phase ultérieure : résoudre et énoncer le chemin absolu du worktree, vérifier la branche exacte. Worktree manquant, mauvaise branche, HEAD détaché ou double nom de branche = arrêt immédiat.

Un agent, un répertoire. Pendant qu'un agent possède un répertoire, aucun autre agent ni le contexte principal ne peut y éditer, checkout ou stasher.

## IDs de story et branches

- Chaque story a un id : `s<number>-<short-slug>` (ex: `s03-progressive-correction`). Assigné dans `docs/stories.md`, réutilisé partout : `docs/research/<id>.md`, `docs/plans/<id>.md`, `docs/reviews/<id>.md`, branche `feature/<id>`.
- Tout le travail d'une story se fait sur `feature/<id>`, branchée depuis la branche par défaut. Jamais de commit de story sur la branche par défaut.
- Le diff d'une story = `git diff <default-branch>...feature/<id>`. C'est ce que la review juge.
- Une commande qui reçoit un nom flou le résout via `docs/stories.md` ; si pas de match unique, lister les stories disponibles et s'arrêter.

## Gate (mécanique)

- Le rapport de review `docs/reviews/<id>.md` doit terminer par les lignes exactes `Max severity: <critical|major|minor|none>` et `Ship allowed: <yes|no>`. Un seul critical = non.
- `/ks-ship` refuse de tourner si ce fichier manque ou contient `Ship allowed: no`. Pas d'exception.
- Après une review bloquée, `/ks-execute` tourne en mode fix : les findings sont remontés à l'implémenteur et corrigés avant tout.
- Un plan s'exécute uniquement si son frontmatter contient `validated: yes` (mis par le checkpoint humain `/ks-plan` ou l'orchestrateur, jamais par le simple fait que le fichier existe).

## Stratégie de ship

Mode de merge : **manuel** (défaut).

- `manuel` : `/ks-ship` ouvre la PR et s'arrête. Le merge est une décision humaine (revue sur GitHub, branche protégée, CI).
- `auto` : `/ks-ship` merge et déploie immédiatement après le gate. Réservé aux flux solo.

## Source de vérité technique

Le `CLAUDE.md` à la racine fait foi pour la stack, l'architecture, le multi-tenancy, le scoring, le RBAC, l'observabilité, l'i18n et l'accessibilité. Toute décision structurelle nouvelle est consignée dans `docs/decisions/NNN-<slug>.md` (format MADR, voir `@templates/adr.md`). Une décision est immuable : un changement = nouvel ADR qui supersede l'ancien.

## Technical conventions

Conventions imposées par `docs/architecture.md` et les ADR. Toute déviation doit être justifiée par un nouvel ADR (cf. `templates/adr.md`).

### Backend (Python)

- **Endpoints FastAPI** : un sous-dossier par domaine dans `app/api/`. Un `router.py` par sous-domaine, des schémas Pydantic pour les entrées/sorties.
- **Services** : un sous-dossier par service dans `app/services/`. Pas de logique métier dans les routers — ils délèguent aux services.
- **Agents LangGraph** : un fichier par agent dans `app/services/agents/`. Le superviseur est un fichier dédié. Les agents reçoivent le `pseudo` du JWT en paramètre explicite.
- **Nommage** : snake_case fichiers/fonctions, PascalCase classes, kebab-case URLs (`/documents/upload`, `/evaluations/score-manual`).
- **Typage** : obligatoire. Pydantic pour les schémas. `Optional` ou `X | None` selon la version Python.
- **Async** : `async def` pour I/O-bound (DB, HTTP, ChromaDB). `def` sync pour CPU-bound.
- **Logs** : `loguru` JSON structuré. Champs : `timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`. Jamais de mot de passe, de token, ou de contenu de document dans les logs.
- **Erreurs** : `HTTPException` FastAPI. Pas de `try/except` muets — toujours logger.
- **Tests** : `pytest`. Un test par AC. Tests d'isolation cross-tenant obligatoires pour tout endpoint touchant des données élève.

### Frontend (TypeScript)

- **Next.js 16 App Router** : routes groupées par `(public)/[locale]/` (pré-JWT, s11a-s11c), `(auth)/` (login/register, s12), `(dashboard)/` (authentifié, s15+). Un dossier par route avec `page.tsx` (+ `layout.tsx` si sous-section). Cf. ADR 006 + recherche s11 Q3 (le story s11a a tranché `(public)` au lieu de `(auth-less)`).
- **Composants** : PascalCase, un composant par fichier, props typées.
- **Hooks** : `useXxx`. Zustand pour le state global (préféré à Context).
- **Stores Zustand** : un store par domaine (`authStore` livré s11a, `chatStore` livré s11b, `uploadStore` livré s11c, `notificationsStore` à venir). Hydratation **client-side only** via `hydrate()` après mount (cf. ADR 011). Pas de SSR state Zustand.
- **API client** : `axios` via `apiClient` (`frontend/lib/api.ts`), `baseURL = NEXT_PUBLIC_API_URL`. Pré-JWT (s11a-s11c), le `pseudo` est envoyé dans le `body` (cf. contrats s09 et s10) ; en s15, l'interceptor JWT ajoute `Authorization: Bearer <token>` (refresh automatique sur 401) et le `pseudo` quitte le body pour le header.
- **Identité transitoire** : `pseudo` en cookie `path=/; max-age=30d; SameSite=Lax` posé par `<Header>`, lu par `useAuthStore.hydrate()`. Regex client `^[a-zA-Z0-9_]{3,32}$` alignée sur le service backend. Cf. ADR 011.
- **i18n** : `useTranslations()` de `next-intl` partout. Aucune string en dur (vérifié par `frontend/scripts/check-i18n.sh`).
- **Styling** : Tailwind v4 + design tokens en CSS variables (cf. `docs/design-system.md`). Pas de CSS modules. Pas de styled-components.
- **Tests** : Playwright (e2e + a11y via `@axe-core/playwright`). Configuration dans `frontend/playwright.config.ts`. Tests dans `frontend/e2e/*.spec.ts`.
- **Accessibilité** : `<label htmlFor>` systématique, `aria-live="polite"` sur les streams (cf. `<StreamingMessage>`), `aria-disabled` + `tabindex="-1"` sur les boutons désactivés (cf. design-system l.228), focus visible (`:focus-visible` Tailwind), contraste AA.
- **Composants UI** : les composants partagés vivent dans `frontend/components/` (`Button`, `Card`, `FileUpload`, `Header`, `Input`, `Label`, `LanguageSwitcher`, `Select`, `StreamingMessage`). Un composant par fichier. Props typées via interface exportée. Pas de logique métier dans un composant partagé.

### Multi-tenancy (transverse)

- **PostgreSQL** : `student_pseudo` sur toutes les tables métier. Toutes les requêtes filtrent par ce champ, extrait du JWT (jamais du body/URL).
- **ChromaDB** : convention `rag_<subject>_<pseudo>`. Factory `get_chroma_collection(subject, pseudo)` (cf. ADR 004).
- **SeaweedFS (S3-compatible, remplace MinIO depuis s01b, cf. ADR 009)** : préfixe `students/<pseudo>/<document_id>`. `document_id` est un UUID. SDK Python `minio>=7.2` (l'API est compatible malgré le rename).
- **JWT** : `sub` = pseudo, `role` = "eleve" | "parent" | "admin". Middleware FastAPI vérifie le `pseudo` du JWT vs URL/body.
- **Tests d'isolation** : un test cross-tenant minimum par story API accédant à des données élève.

### LLM et agents

- **Provider LLM** : sélectionné via `LLM_PROVIDER` env. Par défaut : Minimax-M3 (gratuit, local). Alternatives : OpenAI, Mistral, Ollama.
- **Embeddings** : FastEmbed (ONNX, local) par défaut, OpenAI en alternative.
- **LLM vision** : GPT-4o ou Gemini pour l'OCR manuscrit et l'extraction de score.
- **Temperature** : 0 pour les tests, 0.3 par défaut en prod.
- **Streaming** : `astream_events` (LangChain) pour le chat, exposé en SSE par FastAPI.
- **Structured output** : JSON mode ou function calling quand supporté, sinon parsing strict avec regex.
- **Pas de général knowledge** : les agents répondent UNIQUEMENT à partir des chunks RAG. Le prompt système doit l'exiger explicitement.

### Tests

- **Un test par AC** : chaque critère d'acceptation devient un test exécutable.
- **Stub LLM pour les unit tests** : `FakeListLLM` de LangChain. Les tests d'intégration avec vrai LLM sont best-effort (non bloquants pour la PR).
- **Tests d'isolation cross-tenant** : obligatoires pour toute story API accédant à des données élève (cf. AGENTS.md § Définition of Done).
- **Tests a11y** : Playwright + `@axe-core/playwright` sur les pages principales (s11, s22).
- **Lighthouse** : score a11y ≥ 90 sur les pages principales (config dans `frontend/lighthouserc.json`). Couvre `/`, `/chat`, `/upload` (s11, s22), `/dashboard/*` (s16, s22), `/history` (s19, s22).

### Git et PR

- **Conventional commits** : `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`. Scope entre parenthèses si utile : `feat(api): add /documents/upload`.
- **Branches** : `feature/<story-id>` (jamais sur la branche par défaut). Cf. AGENTS.md § IDs de story et branches.
- **PR unique par story** : description structurée (résumé, AC cochées, captures si UI, points d'attention).
- **Pas de commit de story sur la branche par défaut** : tout passe par PR + merge manuel (mode de merge par défaut).

## Définition of Done (par feature)

- Une PR unique, description structurée, diff lisible
- Tests passants sur la logique métier
- Pas de régression sur le code existant
- **Multi-tenancy vérifié** : au moins un test d'isolation cross-tenant pour toute nouvelle route accédant à des données élève
- **Observabilité conforme** : logs structurés + métriques + traces pour le nouveau code (suivre les conventions de la section Observabilité du `CLAUDE.md`)
- **i18n** : aucune string en dur dans le frontend (toutes via `next-intl`)
- **Accessibilité** : responsive testé (smartphone ≥ 360px, tablette ≥ 768px), contraste et focus visible respectés
- Review passée (aucun critical ouvert)
