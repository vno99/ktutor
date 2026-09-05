---
name: review-s20-systeme-recompenses
description: s20-systeme-recompenses — anti-hallucination review verdict (major findings, ship blocked)
---

# Review — Story s20-systeme-recompenses

> Revu par : sous-agent `reviewer` (contexte frais, analyse du diff `main...feature/s20-systeme-recompenses` dans `.worktrees/s20-systeme-recompenses`).
> Date : 2026-09-05.
> Plan : `docs/plans/s20-systeme-recompenses.md` (`validated: yes`, 14 tâches, split s20a/s20b).
> Design : `docs/designs/s20-systeme-recompenses.md` (badge niveau dans dashboard s16, tokens existants uniquement).
> Diff : `git diff main...feature/s20-systeme-recompenses` (19 fichiers, 1310 insertions, 9 suppressions).

## Verdict

**Ship allowed: no** — 3 findings `major` (interdit observabilité + régression tests dashboard + mutation faible non mordante) ; 2 `minor`.

Le code est fonctionnel (toutes les 14 tâches du plan implémentées, `progressive.py` non touché, `SELECT ... FOR UPDATE` présent, multi-tenant respecté, design-system non inventé). Cependant, le gate mécanique (`Ship allowed: yes`) exige zéro `critical` et aucun `major` non résolu sur un interdit du plan ou sur la cohérence technique. Ici, le `major` sur l'observabilité (`loguru` non utilisé) et la régression sur 3 tests dashboard bloquent la livraison jusqu'à correction.

Max severity: major
Ship allowed: no

---

## Findings détaillés

### Major — `rewards/ledger.py` : format de log non conforme (interdit du plan § Observabilité)

Le service `rewards/ledger.py` utilise `logging.getLogger(__name__)` au lieu de `loguru`. Le plan exige explicitement : `loguru` JSON structuré avec les champs `timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`, `duration_ms`. Le code actuel logue via le logger Python standard sans format JSON et sans ces champs.

**Fix attendu** : remplacer `import logging; logger = logging.getLogger(__name__)` par `from loguru import logger` et s'assurer que chaque appel de log dans le service (`award_points`, lecture) inclut au minimum `request_id` et `pseudo`. Vérifier par lecture du fichier après correction.

### Major — `rewards/ledger.py` : mutation `+=` → `=` ne mord pas (test AC8 faible)

Le test `test_ledger_append_only_no_update_existing_row` (AC8) ne vérifie pas vraiment l'append-only : il teste uniquement `not hasattr(svc, "update_ledger")`. Une mutation qui remplace `user_points_row.total_points += points` par `= points` (overwrite au lieu d'accumulation) n'a produit **aucun test rouge** (`0 red` sur 9 tests de la suite rewards). Cela signifie que le comportement d'accumulation (`+=`) n'est pas testé de manière mordante : le test doit échouer si la ligne est remplacée par un overwrite.

**Fix attendu** : ajouter un test qui lit le `total_points` avant et après attribution et vérifie `after == before + delta`. Ce test doit échouer avec la mutation (`=`). Vérifier que `SELECT ... FOR UPDATE` est présent dans le code source (`ledger.py`) après correction.

### Major — `dashboard/aggregator.py` + `schemas.py` : régression sur 3 tests existants

L'ajout des champs `total_points` et `level` dans `GlobalSummary` / `SubjectSummary` casse 3 tests existants du dashboard :
- `test_response_serializes_with_global_alias_in_json`
- `test_returns_empty_when_eleve_has_no_attempts`
- `test_aggregator_compiles_cast_is_success_as_float`

Le reviewer a confirmé que ces échecs sont causés par la présence des nouveaux champs dans le schéma Pydantic (le payload sérialisé change) et non par un bug métier. C'est une régression acceptable mais bloquante selon le pipeline (`/ks-execute` exige que la suite passe avant `Ship allowed: yes`).

**Fix attendu** : mettre à jour les assertions des 3 tests existants pour inclure les nouveaux champs (`total_points`, `level`) dans la comparaison du payload. Vérifier que la suite complète (`pytest backend/tests/`) passe après correction.

---

### Minor — `rewards/ledger.py` : `logger.info(...)` ne logue pas `exercise_id`

Le log du service `award_points` inclut `points`, `attempt`, `success`, `pseudo` mais pas `exercise_id`. Cela est acceptable selon l'interdit du plan (pas de contenu d'exercice dans le log), mais une meilleure traçabilité serait souhaitable (le `exercise_id` n'est pas sensible au même titre que le contenu de l'exercice).

**Fix attendu** (optionnel, non bloquant) : ajouter `exercise_id` dans le message de log si le niveau `major` est résolu ; sinon laisser en l'état.

---

### Minor — `exercises/router.py` : `_stub_grader` minimal

Le stub `_stub_grader` dans le router `POST /exercises/submit` utilise `bool(body.answer and body.answer.strip())`. C'est une approximation acceptable pour le scope minimal du router (le plan demande un router minimal, pas un grader complet — le grading est délégué au service `ProgressiveCorrectionService`). Aucune action requise.

---

## Interdits vérifiés (conformes)

| Interdit (plan) | Vérification |
|---|---|
| `progressive.py` non touché | `git diff` vide sur le fichier ; lecture complète confirme aucune modification |
| `qcm_grader.py` / `text_grader.py` non touchées | Diff vide sur ces fichiers |
| Design system : pas de token inventé (`--color-level-*`) | `LevelBadge.tsx` utilise `primary` / `success` / `accent-warm` ; aucun nouveau token dans `frontend/app/globals.css` |
| Design system : pas de nouveau composant au-delà de `LevelBadge` | Seul `LevelBadge.tsx` créé dans `frontend/components/` |
| Router `exercises/` avec RBAC (`require_role(["eleve"])`) + JWT pseudo guard | `router.py` contient `require_role(UserRole.ELEVE)` et `assert_jwt_pseudo_matches_or_403` |
| `SELECT ... FOR UPDATE` sur `UserPoints` | `ledger.py` contient `.with_for_update()` dans la transaction |
| Observabilité : `loguru` JSON | **NON CONFORME** — voir Major ci-dessus |
| Multi-tenant : `student_pseudo` FK sur `RewardLedger` | `models.py` contient `student_pseudo` FK sur `RewardLedger` et `UserPoints` |
| Cross-tenant : filtre `pseudo` dans `aggregator.py` | `aggregator.py` filtre `RewardLedger.student_pseudo == pseudo` |
| Split s20a/s20b respecté | `models.py`/`rewards/` (s20a) et `LevelBadge.tsx`/`dashboard/` (s20b) identifiés séparément dans le diff |

---

## Non vérifié (avec gestes humains requis)

- **Visual responsive** (`LevelBadge.tsx`) : pas de test Playwright lancé. Un humain doit ouvrir `/dashboard/eleve` dans un viewport 360px et 768px et vérifier le rendu (`flex-col` / `flex-row`), le contraste AA, le focus visible (`:focus-visible`), et `aria-label` sur le badge.
- **Cross-tenant HTTP** : pas de test HTTP qui fait un second JWT (`pseudo` différent) et confirme que le dashboard retourne 0 ou le total de cet autre pseudo. Un humain doit créer un second JWT et vérifier le filtre.
- **Concurrence `FOR UPDATE`** : SQLite in-memory ne simule pas la contention réelle. Un humain doit lancer deux threads ou inspecter le comportement sous charge.
- **Log format `loguru`** : pas d'appel réel au service (`POST /submit`) avec inspection du `stderr`. Un humain doit déclencher le endpoint et vérifier le format JSON (`timestamp`, `level`, `message`, `request_id`, `pseudo`, `route`).
- **End-to-end submit → points → badge** : nécessite un vrai `ProgressiveCorrectionService` avec un vrai LLM ; best-effort uniquement. Un humain doit faire le test manuel après correction.

---

## Verdict final

Le code respecte la structure du plan, le design-system et le multi-tenant. 3 `major` (observabilité, mutation non mordante, régression dashboard) doivent être corrigés avant livraison. Une fois corrigés, le `Ship allowed` passe à `yes`.

Max severity: major
Ship allowed: no
