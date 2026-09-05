---
name: research-s20-systeme-recompenses
description: s20-systeme-recompenses — research output for /ks-plan
metadata:
  type: project
  story: s20-systeme-recompenses
---

# Research — Story s20-systeme-recompenses

> **Statut** : phase Research. Cible de la phase Plan (`docs/plans/s20-systeme-recompenses.md`).
> **Worktree** : `C:\Workspace\ktutor\.worktrees\s20-systeme-recompenses` (branche `feature/s20-systeme-recompenses`).
> **Source de vérité** : `CLAUDE.md` § Gamification / Récompenses + `docs/stories.md:977-1011`.
> **Date de recherche** : 2026-09-05.

## Les cinq faits structurants

1. **`bonus_points` existe déjà dans `CorrectionResult` (s08) — mais rien n'est persisté.** `backend/app/services/correction/progressive.py:293` calcule `bonus_points = 2 if is_success and attempt_number == 1 else 0`. Le commentaire du module (l.29-30) et la s08 review (l.79) confirment : *« The service does NOT persist anything to `reward_ledger` — s20 will consume `bonus_points` from the `CorrectionResult` »*. **Le hook de consommation est là, le consommateur (ledger) est absent.**

2. **`RewardLedger` et `UserPoints` n'existent aucunement.** `grep -i` sur `backend/app/core/database/models.py` (lignes 1-518) ne trouve aucune occurrence de `reward`, `UserPoints`, `RewardLedger`, `points`, `level`, `apprenti`, `confirme`, `expert`. Le dossier `backend/app/services/rewards/` n'existe pas. **Le modèle de persistance et le service d'attribution sont à créer de zéro.**

3. **`Attempt` (s04/s08) est le source d'entrée fiable.** `models.py:186-233` définit `Attempt` avec `exercise_id`, `student_pseudo`, `attempt_number`, `is_success`, `raw_answers`, `answer_text`, `correction_level`, `submitted_at`. C'est la table qui porte l'historique des tentatives. **Le ledger doit s'écrire à partir de cet historique**, pas remplacer l'`Attempt`.

4. **La gate `max_correction_attempts = 3` est déjà câblée, et le 409/closed aussi.** `backend/app/core/config.py:154` a `max_correction_attempts: int = 3`. `progressive.py:265-272` lève `ProgressiveCorrectionError(kind="closed")` si `attempt_number > 3`. **Le mécanisme de fermeture d'exercice après 3 échecs est prouvé (tests s08 AC9)** — s20 n'a pas à le réimplémenter, seulement à le consommer (ne pas attribuer de points si fermé).

5. **Le dashboard `s16` n'expose ni points ni niveau.** `backend/app/services/dashboard/aggregator.py` calcule `score_avg`, `exercises_count`, `last_activity_at`. `backend/app/api/dashboard/schemas.py` définit `SubjectSummary` / `GlobalSummary` sans champ `total_points` ni `level`. `backend/app/api/dashboard/eleve.py:30-32` mentionne que `app.api.exercises.router` (qui n'existe pas) appelle `invalidate_dashboard`. **Le dashboard doit être étendu pour afficher le niveau (badge).**

## Cible — Story s20-systeme-recompenses

**Story** : s20-systeme-recompenses — Gagner des points en réussissant des exercices.
**Complexité annoncée dans `docs/stories.md`** : **3** (points ledger + level/threshold logic + frontend badge component).
**Complexité réévaluée (vérifiée par lecture du code)** : **4** — raison : s20 doit créer le modèle `RewardLedger` + `UserPoints`, le service `rewards/`, intégrer dans un submit endpoint (`exercises/` HTTP manque), étendre le schéma `EleveDashboardResponse`, et produire un composant badge frontend. C'est un périmètre transverse (DB + service + API + UI) avec 4 surfaces indépendantes. **Proposition de split ci-dessous (§ Décisions d'architecture D1).**

### Acceptance criteria (8 ACs, recopiés depuis `docs/stories.md:985-994`)

- [ ] AC1 — Submitting a successful QCM or text answer awards 5 base points.
- [ ] AC2 — A first-try success (`attempt_number = 1`) awards 5 + 2 = 7 points (bonus).
- [ ] AC3 — A failed attempt awards 0 points (participation only — but the attempt is still recorded in the `Attempt` table).
- [ ] AC4 — After 3 failed attempts, the full correction is shown but no points are awarded. The exercise is then CLOSED — a 4th submission returns 409 (see s08).
- [ ] AC5 — Points are stored in a `RewardLedger` (immutable log) and a `UserPoints` summary.
- [ ] AC6 — The dashboard shows the current points total and the level (e.g. "Apprenti" 0-99, "Confirmé" 100-499, "Expert" 500+).
- [ ] AC7 — A test verifies the points awarded for each scenario (1st-try success: 7, later success: 5, failure: 0, 3 failures + closed: 0).
- [ ] AC8 — A test verifies the ledger is append-only (no UPDATE on existing rows).

### Dépendances (story s20)

| ID | Statut | Ce que s20 en tire | Vérifié ? |
|---|---|---|---|
| **s04** (répondre QCM) | SHIPPÉ (`docs/reviews/s04-repondre-qcm.md` `Ship allowed: yes`) | `QcmGrader.grade()` produit `is_success`, `attempt_number`. `Attempt` persité. | ✅ service + tests (189) |
| **s07** (répondre texte libre) | SHIPPÉ (review passée) | `TextGrader.grade()` produit le même contrat. | ✅ service + tests (37) |
| **s08** (correction progressive) | SHIPPÉ (`89a2535`, review `Ship allowed: yes`) | `ProgressiveCorrectionService.evaluate()` produit `CorrectionResult` avec `is_success`, `attempt_number`, `bonus_points`. `max_correction_attempts = 3` et `closed` (409) prouvés. **LE SERVICE NE PERSISTE PAS DE POINTS.** | ✅ 41 tests |
| **s16** (dashboard élève) | SHIPPÉ (`docs/reviews/s16-dashboard-eleve.md`) | `aggregate_eleve_dashboard()` fournit le payload. **N'a pas `total_points` / `level`.** | ⚠️ extension nécessaire |
| **s04/s07/s08 endpoints HTTP** | **MANQUANT** — `app/api/exercises/` n'existe pas | Le contrat `POST /exercises/submit` (qui déclencherait le calcul des points) n'est pas wire-able en HTTP sans créer le router. | ❌ **trouvé vide par glob** |

**Constat critique** : la dépendance s04/s07/s08 est technique (les services sont livrés et testés), mais le **routage HTTP** (`submition endpoint`) est absent. Le `dashboard/eleve.py:30-32` fait référence à `app.api.exercises.router` comme conditionnel, ce qui confirme que le plan s16 anticipait un router `exercises/` jamais créé. **Pour s20, cela signifie que l'intégration « submit → calcul points » ne peut pas être testée en end-to-end via HTTP sans d'abord créer le router.**

## Code existant à réutiliser

### 1. `ProgressiveCorrectionService` / `CorrectionResult` (s08 — consommateur du hook)

- **Fichier** : `backend/app/services/correction/progressive.py`.
- **Hook pertinent** : ligne 293 (`bonus_points`) et le retour `CorrectionResult(bonus_points=...)` ligne 360-372.
- **Contract de consommation** : s20 doit recevoir `CorrectionResult` (ou `is_success` + `attempt_number`) et écrire dans `RewardLedger`. **Le service s08 ne doit PAS être modifié** (run interdict — il est livré et testé).
- **Le calcul des points est externalisé** : s08 calcule `bonus_points` (2 si first-try success) ; s20 calcule `base_points = 5` si `is_success`, `0` sinon, et additionne `bonus_points` → 7 / 5 / 0.

### 2. `Attempt` model (s04/s08 — source d'entrée historique)

- **Fichier** : `backend/app/core/database/models.py:186-233`.
- **Usage pour s20** : vérifier `attempt_number` et `is_success` si le submit endpoint n'est pas disponible ; sinon, le submit endpoint passe directement `is_success` au service rewards.
- **Multi-tenant** : `student_pseudo` FK (`ondelete="CASCADE"`) — le `RewardLedger` doit avoir le même FK et filtrer par `student_pseudo` dans toutes ses requêtes.

### 3. `max_correction_attempts` (s08 — déjà dans Config)

- **Fichier** : `backend/app/core/config.py:154`.
- **Usage s20** : si `attempt_number > 3` (ou si `correction_level == "full_after_attempts"`), ne pas attribuer de points (AC3/AC4 : 0 points après échec 3e + fermé). La logique est : `if is_success: points = 5 + bonus_points else: points = 0`, et en plus `if attempt_number > 3: points = 0` (sécurité).

### 4. `aggregate_eleve_dashboard()` (s16 — extension nécessaire)

- **Fichier** : `backend/app/services/dashboard/aggregator.py`.
- **Extension attendue** : ajouter `SUM(points)` depuis `RewardLedger` et `level` (calculé depuis la somme) dans `GlobalSummary` et `SubjectSummary`. Ou créer une requête séparée.
- **Le `dashboard/eleve.py` mentionne** que `invalidate_dashboard` est appelé par le router exercices (qui n'existe pas) — s20 doit ajouter cet appel si un endpoint submit est créé.

### 5. `next-intl` / design tokens (frontend — badge)

- **Source** : `docs/design-system.md` (existe, lu par le worktree-manager au bootstrap).
- **Usage** : le composant badge de niveau doit utiliser le design token (couleur « Apprenti » = bleu, « Confirmé » = vert, « Expert » = jaune/or) défini dans `docs/design-system.md`. **Pas d'invention de token** — cf. AGENTS.md § Design system.

## Contraintes techniques

### Multi-tenancy (transverse — AGENTS.md § Multi-tenancy)

- **PostgreSQL** : `student_pseudo` FK sur `RewardLedger` et `UserPoints`. Toutes les requêtes filtrent par `student_pseudo` (extrait du JWT, jamais du body/URL).
- **Isolation cross-tenant** : au moins un test doit vérifier qu'un élève A ne peut pas lire les points/levels de B.
- **ChromaDB / S3** : non touchés par s20 (pas de documents ni d'embeddings dans cette story).

### Ledger immuable (AC8)

- **Source** : `docs/stories.md:1005-1006` + agentic notes s20.
- **Règle** : `RewardLedger` est le **source de vérité** ; `UserPoints` est une **dénormalisation**, recalculable depuis le ledger.
- **Implémentation** : pas de `UPDATE` sur une ligne `RewardLedger`. Seul `INSERT`. Le `UserPoints` est mis à jour via `UPDATE` (ou `INSERT ... ON CONFLICT`) dans la même transaction que l'écriture du ledger.
- **Concurrence** : deux soumissions parallèles sur le même `(pseudo, exercise_id)` doivent être sérialisées par un `SELECT ... FOR UPDATE` sur `UserPoints` (ligne 1008 de stories.md : *"Use a DB transaction with row-level locking on UserPoints"*).

### Scoring (AC1-AC4)

- **Base** : 5 points si `is_success` est `True`. 0 si `False`. **Pas de points « participation »** pour un échec — le AC3 dit explicitement *"A failed attempt awards 0 points (participation only — but the attempt is still recorded in the `Attempt` table)"*. L'`Attempt` est enregistré par s08, le ledger ne reçoit rien (0 points).
- **Bonus** : +2 si `is_success` ET `attempt_number == 1`. Sinon +0. **Le bonus est conditionné au premier essai réussi**, pas à tout succès.
- **Fermé (AC4)** : après 3 échecs, l'exercice est `full_after_attempts`. Une 4e tentative donne `ProgressiveCorrectionError("closed")` (409). Même si le submit parvenait à passer (ce qui n'est pas le cas car le service rejette), s20 doit ne pas écrire dans le ledger (points = 0).

### Niveaux / seuils (AC6)

- **Apprenti** : 0 – 99 points.
- **Confirmé** : 100 – 499 points.
- **Expert** : 500+ points.
- **Constantes** : pour le POC, fixes dans le code. Si changées, recalculer `UserPoints` depuis `RewardLedger`.
- **Badge frontend** : afficher le texte du niveau + un indicateur visuel (couleur / icône) basé sur le total.

### Log / Observabilité (CLAUDE.md § Observabilité)

- **Logs structurés** : `loguru` JSON. Champs : `timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`. Jamais le contenu de l'exercice ni le contenu du ledger dans le log (données sensibles indirectes via le pseudo).
- **Métrique Prometheus** (optionnel mais conforme) : `rewards_total_points{pseudo}` et `rewards_ledger_entries_total` si un endpoint `/metrics` est déjà exposé.

## Décisions d'architecture (à trancher au plan, format MADR si nécessaire)

### D1. Split de s20 (recommandé — car complexité réelle est 4 et périmètre transverse)

- **Option A** : s20 reste une seule story (modèles + service + router submit + dashboard + badge). Risque : trop grand pour un cycle unique (plan > 10 tasks), risque d'échec de la review.
- **Option B** (recommandé) : **s20a — Système de récompenses (DB + service)** : `RewardLedger`, `UserPoints`, `rewards/ledger.py`, `rewards/levels.py`, tests, intégration avec le submit (via un router minimal `exercises/submit` ou un appel depuis le CLI). **s20b — Badge niveau + dashboard points + i18n** : extension `dashboard/schemas.py`, `aggregator.py`, composant frontend, tests Playwright.
- **Justification** : s08 a entré le hook dans le service. S20a consomme le hook. S20b consomme le résultat de s20a. La séparation permet de livrer le ledger (valeur métier immédiate) indépendamment du badge (valeur UX). **Le split est cohérent avec AGENTS.md § Pipeline (une feature = une PR)**.

### D2. Integration du submit (router `exercises/` — manque)

- **Option A** : créer `backend/app/api/exercises/router.py` (POST `/api/exercises/submit`) dans s20a, avec le service rewards appelé après `ProgressiveCorrectionService`.
- **Option B** : laisser le submit en CLI uniquement (`submit-qcm` / `submit-text`) et faire appel au service rewards via CLI. **Moins utile pour le devant** (badge ne se met pas à jour sans appel API).
- **Recommandation** : **Option A** pour s20a, avec un router minimal (`POST /api/exercises/submit`) qui prend `exercise_id`, `answer`, délègue au grader (`qcm_grader` / `text_grader` — ou au service `ProgressiveCorrectionService` s'il est déjà injecté), puis au service rewards. **Le router doit respecter le multi-tenant (JWT `sub` = pseudo)** et le RBAC (`require_role(["eleve"])`) — cf. `CLAUDE.md` § Permissions.

### D3. Source de vérité du score (ledger vs `Attempt`)

- **Option A** : le `RewardLedger` est écrit uniquement par le service rewards (appelé après submit). `Attempt` reste indépendant.
- **Option B** : le `Attempt` est la source de vérité du score de la tentative ; le ledger est un journal audit des attributions (chaque ligne = 1 attribution de points). **Option B est plus robuste** (on peut reconstruire le total depuis `Attempt.is_success` + `attempt_number`, mais le AC8 demande un ledger immuable séparé).
- **Recommandation** : **Option B** — `RewardLedger` reçoit une ligne par attribution (`exercise_id`, `student_pseudo`, `points_awarded`, `attempt_number`, `is_success`, `created_at`). `UserPoints` est mis à jour par `UPDATE ... SET total_points = total_points + :delta`. La reconstruction est possible mais le ledger reste l'audit trail.

### D4. Calcul du niveau — côté DB ou côté service

- **Option A** : `UserPoints` stocke `total_points` + `level` (dénormalisé). Mis à jour à chaque attribution.
- **Option B** : `UserPoints` stocke seulement `total_points`. Le niveau est calculé au moment de la lecture (service `levels.get_level(points)`). **Plus propre** (pas de risque de drift du niveau si la constante change).
- **Recommandation** : **Option B** — `UserPoints.total_points` est la seule colonne dénormalisée. `levels.py` calcule le niveau à la lecture. Si les seuils changent, pas besoin de mettre à jour `UserPoints`.

## Fichiers anticipés

> Chaque fichier : nouveau / étendu / non touché.

### Création (s20a — ledger + niveaux + service)

1. `backend/app/core/database/models.py` — **étendu** (+2 modèles : `RewardLedger`, `UserPoints`).
2. `backend/app/services/rewards/ledger.py` — **nouveau** — `RewardLedgerService` (`award_points`, `get_ledger_for_pseudo`, `is_append_only`).
3. `backend/app/services/rewards/levels.py` — **nouveau** — `get_level(points: int) -> str` (Apprenti/Confirmé/Expert), constantes seuil.
4. `backend/app/services/rewards/__init__.py` — **nouveau**.
5. `backend/app/api/exercises/router.py` — **nouveau** (minimal, `POST /submit` — cf. D2 Option A). *Si split s20a/s20b, ce fichier peut être déplacé dans s20b si le router est considéré comme UI.*

### Création (s20a — tests)

6. `backend/tests/services/rewards/test_ledger.py` — **nouveau** — AC7 (scénarios points) + AC8 (append-only).
7. `backend/tests/services/rewards/test_levels.py` — **nouveau** — seuils 0/100/500.
8. `backend/tests/core/test_models.py` — **étendu** (+2 assertions sur `RewardLedger` / `UserPoints` fields, multi-tenant).

### Extension (s20b — dashboard + frontend)

9. `backend/app/services/dashboard/aggregator.py` — **étendu** — requête `SUM(RewardLedger.points_awarded)` + `get_level()`. Ou requête séparée appelée par le router.
10. `backend/app/api/dashboard/schemas.py` — **étendu** — `GlobalSummary` + `SubjectSummary` + `SubjectName` : ajouter `total_points: int = 0`, `level: str = "Apprenti"`.
11. `backend/app/api/dashboard/eleve.py` — **étendu** — appeler le service rewards / aggregator étendu ; invalider le cache si un nouveau submit a eu lieu.
12. `frontend/components/level-badge.tsx` (ou équivalent) — **nouveau** — composant badge avec couleur selon niveau, texte localisé (`next-intl`).
13. `frontend/app/(dashboard)/eleve/page.tsx` — **étendu** — afficher le badge + les points dans la section en-tête du dashboard.

### Non touchés (run interdicts — s08 / s04 / s07 / s16 livrés, pas de régression)

- `backend/app/services/correction/progressive.py` — **non touché** (le hook `bonus_points` est consommé, pas modifié).
- `backend/app/services/exercises/qcm_grader.py`, `text_grader.py` — **non touchés**.
- `backend/app/core/config.py` — **non touché** (déjà `max_correction_attempts = 3`).

## Tests à prévoir (un par AC + cross-tenant)

| AC | Test cible | Type |
|---|---|---|
| AC1 (5 pts succès) | `test_award_5_points_on_success` | service |
| AC2 (7 pts 1er essai) | `test_award_7_points_first_try` | service |
| AC3 (0 pts échec) | `test_award_0_points_on_failure` | service |
| AC4 (0 pts après 3 + fermé) | `test_award_0_points_after_3_failures_closed` | service + state machine |
| AC5 (ledger + UserPoints) | `test_ledger_persisted_and_summary_updated` | service + DB |
| AC6 (dashboard points + niveau) | `test_dashboard_shows_points_and_level` | API / intégration |
| AC7 (scénarios combinés) | `test_all_scenario_points` (parametrized : 7, 5, 0, 0) | service |
| AC8 (append-only) | `test_ledger_no_update_on_existing_row` (mutation : `UPDATE` interdit) | DB / service |
| Cross-tenant | `test_cross_tenant_cannot_read_other_points` | API / service |

**Piège de mutation attendu** (comme s08) : si le service fait `UPDATE RewardLedger SET points = ...` au lieu de `INSERT`, le test AC8 doit échouer. Si le service oublie `SELECT ... FOR UPDATE` sur `UserPoints` et deux threads écrivent en parallèle, le total peut être sous-compté — le test concurrent (si faisable) doit le détecter.

## Pièges identifiés (≥ 4 exigés, complexité réelle 4)

### Piège 1 — Dépendance HTTP manquante (`app/api/exercises/`)

Le `submit` endpoint (`POST /exercises/submit`) est la seule surface qui peut déclencher le calcul des points (via `ProgressiveCorrectionService` puis `RewardLedgerService`). **Le dossier `app/api/exercises/` est vide** (confirmé par `ls backend/app/api/`). Sans créergation de ce router, s20 ne peut pas être testé end-to-end via HTTP — seulement en CLI ou en test unitaire direct. **Mitigation** : soit créer le router dans s20a, soit documenter que s20 est un service backend jusqu'à ce que le router soit livré (par s04/s07/s08 rétrospectivement). **Recommandation incluse dans D2.**

### Piège 2 — Confusion entre `bonus_points` (s08) et `base_points` (s20)

`CorrectionResult.bonus_points` (s08) est `2` au premier essai réussi, `0` sinon. **Le AC s20 demande 5 points de base** + 2 de bonus. Si le service s20 consomme `bonus_points` mais oublie d'ajouter `5`, le score serait 2 au lieu de 7. **Mitigation** : le service rewards doit avoir sa propre logique (`base = 5 if is_success else 0`; `total = base + bonus_points`) et ne pas remplacer le calcul par `bonus_points` seul.

### Piège 3 — `UserPoints` dénormalisé sans verrou transactionnel

Deux soumissions concurrentes sur le même exercice (ou deux exercices différents du même élève) peuvent lire le même `UserPoints.total_points`, ajouter leur delta, et écrire — résultat : perte d'un delta (race condition). **Mitigation** : `SELECT ... FOR UPDATE` sur la ligne `UserPoints` dans la transaction qui fait `INSERT RewardLedger`. Le AC8 (append-only) ne couvre pas la concurrence ; il faut un test séparé si le framework de test le permet (sqlite in-memory ne simule pas la contention, mais le code doit avoir la garde).

### Piège 4 — `Attempt` vs `RewardLedger` : double comptage potentiel

Si le service rewards écrit dans le ledger à chaque `Attempt` (même un échec, 0 points), le ledger contient des lignes à 0 points pour chaque échec. **Le AC5 ne précise pas si un échec doit être dans le ledger** (le AC3 dit « 0 points »). Si le ledger reçoit une ligne à 0 points, c'est un audit trail complet ; si pas, le total reste le même mais l'audit est incomplet. **Mitigation** : écrire toujours dans le ledger (0 points pour échec), car cela rend le `RewardLedger` une source de vérité complète de toutes les tentatives notées. Le `UserPoints` est mis à jour par `delta = 5 + bonus` si succès, `0` sinon.

### Piège 5 — Niveau calculé sur `UserPoints` mais pas sur `Attempt`

Le `EL` (éleve) peut avoir 0 points mais plusieurs `Attempt.is_success = True`. Si le leaderboard/level est calculé sur `Attempt` au lieu de `UserPoints`, le résultat est faux. **Mitigation** : la règle est explicite dans le AC6 — le dashboard montre le niveau basé sur le total des points, pas sur la moyenne des succès. Le `aggregator.py` doit être mis à jour pour joindre `UserPoints`, pas `Attempt` directement.

### Piège 6 — Badge frontend sans design-system match

Le composant badge doit utiliser les tokens du design system (`docs/design-system.md`). Si le développeur invente une couleur `/rgb` au lieu d'utiliser le token `--color-level-expert`, le review va échouer (cf. AGENTS.md § Design system). **Mitigation** : lire `docs/design-system.md` avant d'écrire le composant ; si le token n'existe pas, l'ajouter là-bas d'abord, puis l'utiliser.

### Piège 7 — `next-intl` non configuré pour le label de niveau

Le texte « Apprenti / Confirmé / Expert » est une chaîne UI. Elle doit être dans `frontend/messages/fr.json` et `en.json`. **Le AC6 ne mentionne pas i18n explicitement**, mais AGENTS.md § i18n impose aucune string en dur. **Mitigation** : inclure la traduction dans la tâche du badge (s20b).

## Split proposé (si validé au plan)

| Story | Périmètre | Complexité | Dépendance |
|---|---|---|---|
| **s20a-système-récompenses** | `RewardLedger`, `UserPoints`, `rewards/` service, `post /exercises/submit` (router minimal), tests AC1-AC8 + cross-tenant | 4 | s08 (hook consommé) |
| **s20b-badge-niveau** | `dashboard/schemas.py` + `aggregator.py` (points + niveau), composant `level-badge`, `page.tsx` dashboard, tests a11y / Playwright | 3 | s20a (points disponibles) + s16 (dashboard existant) |

**Recommandation** : valider le split au plan. Si le plan reste unique (s20), il doit dépasser 10 tâches et la complexité doit être documentée comme 4 (pas 3). En l'état du code, s20 ne peut pas être livré sans le router `exercises/` — le split isole ce risque.

## Open questions

1. **Le router `exercises/submit` doit-il être dans s20a ou dans un plan séparé (s04/s07 rétrospectif)** ? Le service s08 est déjà testé en CLI ; le router HTTP est un ajout transverse. Si s20a le crée, il doit respecter RBAC (`require_role(["eleve"])`) et le middleware JWT (`assert_jwt_pseudo_matches_or_403`).
2. **Le `UserPoints` doit-il avoir un `updated_at` ?** Non spécifié dans le AC, mais utile pour le cache du dashboard. Recommandation : oui, `DateTime(timezone=True), server_default=func.now(), onupdate=func.now()`.
3. **Le `RewardLedger` doit-il avoir un `exercise_id` ?** Oui, le AC7 compare par scénario d'exercice ; le ledger doit être filtrable par exercice (pour audit). Recommandation : oui, FK vers `exercises.id`.
4. **Le composant badge doit-il être responsive (smartphone ≥ 360px)** ? Oui, AGENTS.md § Accessibilité impose responsive. À vérifier dans la tâche s20b.

---

*Recherche terminée. Prochaine étape recommandée : `/ks-plan s20-systeme-recompenses` (avec validation du split s20a/s20b si la complexité est confirmée 4).*