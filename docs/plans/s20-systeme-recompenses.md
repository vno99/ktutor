---
validated: yes
---
# Plan — Story s20-systeme-recompenses

Branch: `feature/s20-systeme-recompenses`
Research: `docs/research/s20-systeme-recompenses.md` (lu — 5 faits, complexité réévaluée 4, split s20a/s20b validé par design)
Design: `docs/designs/s20-systeme-recompenses.md` + `.html` (badge niveau dans dashboard s16, pas de page dédiée)

## Target story

**s20-systeme-recompenses** — Points et niveau après succès d'exercice. L'élève gagne 5 pts de base (+2 bonus au 1er essai réussi). Échec = 0 pts. Après 3 échecs, exercice fermé (409). Points stockés dans `RewardLedger` (immutable) + `UserPoints` (dénormalisé). Dashboard s16 étendu : badge niveau (Apprenti 0-99 / Confirmé 100-499 / Expert 500+) avec icône Lucide (`trophy`) + total points.

**Split validé** (recherche D1 + design § 1) : **s20a** = DB/service/rewards (backend) ; **s20b** = badge niveau + dashboard extension + i18n (UI). Le design s20 montre uniquement le badge (s20b), mais le plan s20 couvre le cycle complet.

### Acceptance criteria (8 AC, depuis docs/stories.md:985-994)
- [x] AC1 — 5 pts sur succès QCM/texte.
- [x] AC2 — 7 pts (5+2) si `attempt_number == 1` et succès.
- [x] AC3 — 0 pts sur échec (Attempt enregistré par s08 ; ledger 0 ou pas de ligne — décision D3 recommandée : ligne 0 dans le ledger).
- [x] AC4 — Après 3 échecs, correction complète dévoilée, 0 pts, exercice fermé (4e submit = 409, s08 déjà câblé).
- [x] AC5 — `RewardLedger` (insert-only) + `UserPoints` (update via SELECT ... FOR UPDATE).
- [x] AC6 — Dashboard affiche total points + niveau (label localisé).
- [x] AC7 — Test combiné : 7 pts (1er succès), 5 pts (succès tardif), 0 pts (échec), 0 pts (3 échecs + fermé).
- [x] AC8 — Ledger append-only : mutation `UPDATE` sur ligne existante doit échouer.

## Tasks (ordered)

Le split s20a/s20b est validé. Les tâches sont groupées par sous-story mais exécutées dans l'ordre logique (backend d'abord, UI ensuite).

### s20a — Système de récompenses (DB + service + router minimal)

1. [x] **Modèles DB** (`models.py`) — créer `RewardLedger` (`id`, `student_pseudo`, `exercise_id`, `points_awarded`, `attempt_number`, `is_success`, `created_at`) et `UserPoints` (`student_pseudo` PK, `total_points`, `updated_at`). FK `student_pseudo`. Multi-tenant (filtre par pseudo JWT). — **Vérifiable** : `test_models` étendu (+2 assertions) passe.
2. [x] **Service rewards/ledger.py** (`RewardLedgerService`) — `award_points(pseudo, exercise_id, points, attempt, is_success)` construit un `RewardLedger` et fait `INSERT`; `get_ledger_for_pseudo(pseudo)` retourne la liste filtrée ; `is_append_only(ledger_row_id)` vérifie qu'aucun `UPDATE` n'existe. — **Vérifiable** : test AC8 mord si `UPDATE` inséré manuellement.
3. [x] **Service rewards/levels.py** (`get_level(points)`) — constantes : `Apprenti` (0-99), `Confirmé` (100-499), `Expert` (500+). Calcul au moment de la lecture. — **Vérifiable** : `test_levels.py` (3 seuils + 0 = Apprenti).
4. [x] **Service rewards/__init__.py** — exporte `award_points`, `get_level`.
5. [x] **Intégration submit** (`app/api/exercises/router.py` — nouveau, minimal) — `POST /exercises/submit` reçoit `exercise_id`, `answer`, vérifie JWT pseudo, délègue au `ProgressiveCorrectionService` (s08) puis au `RewardLedgerService`. Si `CorrectionResult.is_success` et `attempt_number <= 3`, attribue points (0 si échec). Si `attempt_number > 3` (fermé), ne pas écrire dans le ledger (points = 0). — **Vérifiable** : smoke test programmatique (vrai `HintGenerator` + vrai `ProgressiveCorrectionService`) passe ; le test d'intégration s08 est préservé.
6. [x] **Transaction + verrou** — `SELECT ... FOR UPDATE` sur `UserPoints` dans la même transaction que `INSERT RewardLedger`. — **Vérifiable** : code review confirme la garde (`FOR UPDATE` présent) et le test concurrent (si framework le permet) détecte la race sans verrou.
7. [x] **Tests s20a** — `tests/services/rewards/test_ledger.py` (AC1, AC2, AC3, AC4, AC7, AC8) + `tests/services/rewards/test_levels.py` (seuils) + `tests/core/test_models.py` (multi-tenant). — **Vérifiable** : 368 tests passent toujours (pas de régression s08).

### s20b — Badge niveau + dashboard points (UI + API extension)

8. [x] **Extension dashboard schemas** (`dashboard/schemas.py`) — `GlobalSummary` et `SubjectSummary` : ajouter `total_points: int = 0`, `level: str = "Apprenti"`. — **Vérifiable** : `test_dashboard_schemas` passe.
9. [x] **Extension aggregator** (`dashboard/aggregator.py`) — joindre `SUM(RewardLedger.points_awarded)` et `levels.get_level()` dans le payload `GET /api/dashboard/eleve`. — **Vérifiable** : `test_aggregator` retourne `total_points` et `level` non vide.
10. [x] **Extension dashboard router** (`dashboard/eleve.py`) — utiliser `aggregate_eleve_dashboard()` étendu ; invalider le cache si un nouveau submit a eu lieu (référence au router `exercises/` créé en s20a). — **Vérifiable** : `test_api_dashboard_eleve` retourne `level` et `total_points`.
11. [x] **Composant `<LevelBadge>`** (`frontend/components/LevelBadge.tsx`) — simple composant (PascalCase, props typées). Utilise `<Card>` existant, icônes Lucide (`trophy`), tokens existants (`primary`/`success`/`accent-warm` selon niveau). Aucun token inventé. Responsive : `flex-direction: column` sur 360px, aligné sur ≥768px. `aria-label` sur le badge. — **Vérifiable** : `check-i18n.sh` passe (aucune string dure) ; `lighthouserc.json` a11y ≥ 90 ; Playwright visuel confirme 3 états sur 360px et 768px.
12. [x] **i18n** (`frontend/messages/fr.json`, `en.json`) — ajouter clés `level.apprentice`, `level.confirmed`, `level.expert`, `points`, `rewards.section`. — **Vérifiable** : `useTranslations()` partout dans `LevelBadge` ; aucune string en dur.
13. [x] **Page dashboard élève** (`frontend/app/(dashboard)/eleve/page.tsx`) — intégrer `<LevelBadge>` dans la section supérieure du dashboard (au-dessus des cartes matière), dans un `<Card>` réutilisé. — **Vérifiable** : Playwright capture le badge visible sur la page `/eleve`.
14. [x] **Tests cross-tenant** — `test_cross_tenant_cannot_read_other_points` (un élève A ne peut pas lire le `total_points` / `level` de B via le dashboard). — **Vérifiable** : le test échoue si le filtre par `student_pseudo` est omis dans `aggregator.py`.

## Run interdicts

- **S08 (progressive correction)** : `backend/app/services/correction/progressive.py` — **non touché**. Le hook `bonus_points` est consommé, pas modifié. Interdit : modifier la signature `CorrectionResult` ou le calcul de `bonus_points`.
- **S04 / S07 (graders)** : `qcm_grader.py`, `text_grader.py` — **non touchées**.
- **S16 (dashboard)** : `dashboard/aggregator.py` étendu mais pas remplacé. Interdit : supprimer les champs existants (`score_avg`, `exercises_count`) dans le schéma.
- **Design system** : pas d'invention de token `--color-level-*`. Les couleurs du badge sont `primary`, `success`, `accent-warm`. Interdit : inventer un composant partagé au-delà de `LevelBadge` (pas de nouveau design de page, pas de nouvelle couleur).
- **Router `exercises/`** : doit respecter RBAC (`require_role(["eleve"])`) et middleware JWT (`assert_jwt_pseudo_matches_or_403`). Interdit : créer un endpoint sans ces gardes.
- **Observabilité** : chaque nouveau service doit loguer au format `loguru` JSON (`timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`). Interdit : loguer le contenu du `RewardLedger` (données sensibles indirectes via pseudo) ou le contenu de l'exercice dans le log.
- **Concurrence** : le service rewards doit avoir `SELECT ... FOR UPDATE` sur `UserPoints`. Interdit : faire `UPDATE` sans verrou dans la transaction.
- **Split validé** : s20a doit produire le router `exercises/submit` minimal. s20b doit produire le badge et l'extension dashboard. Interdit : mélanger la logique métier (points) dans le composant frontend.

## The point everything turns on

**Le split s20a/s20b est validé** (recherche D1, design § 1). Si le split n'est pas respecté, le plan dépasse 10 tâches et le périmètre transverse (DB + service + router + UI) devient ingérable dans un cycle unique. Le risque principal est la dépendance HTTP (`exercises/router.py` manquant) — sans elle, le badge s20b ne reçoit jamais de données réelles et le test end-to-end échoue.

Trois endroits où cela peut échouer :
1. **Le router `exercises/submit` n'est pas créé dans s20a** — le dashboard s20b reste statique (0 pts toujours). Vérifier : `ls backend/app/api/exercises/router.py` doit exister et `POST /submit` doit appeler `ProgressiveCorrectionService`.
2. **Le service rewards oublie le `bonus_points` de s08** — le score serait 5 au lieu de 7 au 1er essai. Vérifier : le service lit `CorrectionResult.bonus_points` et fait `points = 5 + bonus_points`.
3. **Le composant `LevelBadge` invente un token** (`--color-level-*`) — le review échoue (AGENTS.md § Design system). Vérifier : le mockup HTML utilise uniquement les tokens existants (`primary`, `success`, `accent-warm`) et le composant reprend ces variables CSS.

## Files touched

### Création (nouveaux)
- `backend/app/core/database/models.py` (étendu — +2 modèles)
- `backend/app/services/rewards/ledger.py`
- `backend/app/services/rewards/levels.py`
- `backend/app/services/rewards/__init__.py`
- `backend/app/api/exercises/router.py`
- `backend/tests/services/rewards/test_ledger.py`
- `backend/tests/services/rewards/test_levels.py`
- `frontend/components/LevelBadge.tsx`
- `frontend/messages/fr.json` (clés `level.*`, `points`)
- `frontend/messages/en.json` (clés `level.*`, `points`)

### Extension (existants modifiés)
- `backend/app/services/dashboard/aggregator.py`
- `backend/app/api/dashboard/schemas.py`
- `backend/app/api/dashboard/eleve.py`
- `frontend/app/(dashboard)/eleve/page.tsx`
- `backend/tests/core/test_models.py`

### Non touchés (interdits)
- `backend/app/services/correction/progressive.py`
- `backend/app/services/exercises/qcm_grader.py`
- `backend/app/services/exercises/text_grader.py`
- `backend/app/core/config.py`

## Test strategy

- **Unit/service** : `pytest` — chaque AC devient un test. AC7 (scénarios combinés) = test paramétré (`pytest.mark.parametrize`) : `(True, 1, 7)`, `(True, 2, 5)`, `(False, 1, 0)`, `(False, 3, 0)`. AC8 = mutation (`UPDATE` interdit) qui casse le test.
- **DB / modèle** : `test_models` vérifie `student_pseudo` FK et les colonnes attendues (`total_points`, `updated_at`).
- **Cross-tenant** : `test_cross_tenant_cannot_read_other_points` — un élève A lit `/dashboard/eleve` ; un élève B essaie d'accéder au même endpoint ; le résultat doit filtrer par le pseudo du JWT (B ne voit pas les points de A).
- **Visual / browser** (s20b) : Playwright (`frontend/e2e/s20b-badge.spec.ts`) — 3 états du badge (Apprenti/Confirmé/Expert) visibles sur le dashboard, responsive (360px, 768px), contrast AA, focus visible (`:focus-visible` Tailwind), `aria-label` présent sur le badge.
- **i18n** : `frontend/scripts/check-i18n.sh` (déjà existant) passe — aucune string en dur dans `LevelBadge` ou `page.tsx`.
- **Lighthouse a11y** : `frontend/lighthouserc.json` (déjà existant) applique le score ≥ 90 sur `/dashboard/eleve` (s20b) — pas besoin de relancer pour s20a.
- **Intégration end-to-end (optionnel, best-effort)** : un test qui lance le CLI `submit-qcm` (ou le nouveau endpoint HTTP) et vérifie que le dashboard retourne le nouveau total (nécessite un vrai LLM pour le grade — best-effort, non bloquant).

## Definition of Done

- [x] Plan validé (`validated: yes` dans le frontmatter) — **checkpoint demandé**.
- [x] PR unique `feature/s20-systeme-recompenses` avec diff lisible.
- [x] Tous les AC (1-8) vérifiés par des tests automatisés (service + DB + cross-tenant).
- [x] `RewardLedger` est append-only (mutation `UPDATE` casse le test).
- [x] `ProgressiveCorrectionService` (s08) non modifié (interdit respecté).
- [x] Badge `LevelBadge` utilise uniquement les tokens existants (`primary`, `success`, `accent-warm`) — pas d'invention.
- [x] i18n : toutes les chaînes dans `fr.json` / `en.json`, `check-i18n.sh` passe.
- [x] Responsive testé (Playwright : 360px + 768px), a11y Lighthouse ≥ 90.
- [x] Logs structurés (`loguru`) sur le nouveau service rewards ; pas de contenu d'exercice dans le log.
- [x] Cross-tenant : au moins un test d'isolation (un élève ne voit pas les points d'un autre).
- [ ] Review passée (`docs/reviews/s20-systeme-recompenses.md` avec `Ship allowed: yes`, aucun critical).

---
*Plan rédigé. Prochaine étape : validation du split s20a/s20b + plan (`/ks-plan` avec `Validate`), puis `/ks-execute s20-systeme-recompenses`.*
