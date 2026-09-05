---
id: s18b-evaluation-actions-admin
title: "Recherche — Saisir ou relancer l'extraction du score d'une évaluation"
status: done
---

# s18b — Recherche

## Story

`docs/stories.md:906-942` — **s18b-evaluation-actions-admin — Saisir ou
relancer l'extraction du score d'une évaluation.**

- **As an** admin (ou un parent lié) **I want** saisir manuellement le score
  d'une copie d'évaluation en `manual_review_needed` (ou relancer
  l'extraction LLM) **so that** les copies sans score détecté puissent tout
  de même alimenter les dashboards.

**Complexité déclarée** : 2.

**Dépendances** : s18 (modèle `Evaluation` + statut `manual_review_needed`),
s14 (`ParentChildLink`), s15 (JWT + RBAC). Toutes livrées.

## Acceptance criteria (verbatim depuis stories.md)

1. `POST /api/evaluations/{id}/score-manual` (admin or linked parent, JWT)
   accepte `{score, max_score, teacher_comments?}` et met à jour la ligne
   `Evaluation`. Retourne 200 avec l'évaluation mise à jour.
2. L'endpoint valide que l'évaluation est en `manual_review_needed` ;
   sinon retourne 409 (déjà scorée).
3. Un appelant non-admin, non-parent lié obtient 403.
4. `POST /api/evaluations/{id}/reprocess` (admin only, JWT) ré-invoque
   l'extracteur LLM vision sur l'image originale. Retourne 200 avec le
   nouveau résultat (ou `manual_review_needed` si toujours KO).
5. Les deux endpoints passent le statut à `scored` en cas de succès, ou
   laissent `manual_review_needed` en cas d'échec.
6. Un test vérifie qu'un admin peut saisir manuellement le score d'une
   évaluation en `manual_review_needed`.
7. Un test vérifie qu'un appelant non-admin, non-parent obtient 403.
8. Un test vérifie l'isolation multi-tenant : un parent ne peut pas
   scorer une évaluation d'un enfant non lié.

## Localisation de la vérité

L'agent a lu le code dans le worktree
`C:\Workspace\ktutor\.worktrees\s18b-evaluation-actions-admin`
(branche `feature/s18b-evaluation-actions-admin`, HEAD `4be99b3`, propre).
Toute la cartographie qui suit provient de cette lecture.

## Prémisse vérifiée (vs dérive du code)

| Fichier / élément attendu | Statut | Note |
| --- | --- | --- |
| `Evaluation` model | ✅ Existe | `app/core/database/models.py:225`. Colonnes : `id` (UUID PK), `student_pseudo` (FK CASCADE), `subject`, `s3_key`, `filename`, `status` (Enum), `score`, `max_score`, `annotations` (JSON), `teacher_comments`, `ocr_text`, `ocr_confidence`, `error_reason`, `created_at`. |
| `EvaluationStatus` enum | ✅ Existe | `models.py:33`. Valeurs `SCORED`, `MANUAL_REVIEW_NEEDED`. Cf. ADR 013. |
| `EvaluationService.upload` (s18) | ✅ Existe | `app/services/ocr/evaluation_extractor.py:273`. Inserts a single row. **Ne fournit PAS** de méthode pour muter un row existant ni pour re-extraire depuis le `s3_key`. |
| `EvaluationExtractor.extract(image_path)` | ✅ Existe | `evaluation_extractor.py:115`. Stateless, synchrone, accepte n'importe quel `_OcrLike` (Protocol). **Réutilisable** pour le reprocess — il suffit d'un path vers l'image. |
| `MinioClient.get_object(key)` | ✅ Existe | `app/services/storage/minio_client.py:62`. Retourne les bytes. Le reprocess peut donc recharger l'image originale. |
| `MinioClient.remove_object(key)` | ✅ Existe | `minio_client.py:73`. Idempotent (ignore `NoSuchKey`). Réutilisable en cas de rollback. |
| `assert_parent_linked_to_child_or_403(user, claimed, route, db)` | ✅ Existe | `app/core/auth/middleware.py:215`. Logge `security.cross_tenant_attempt` sur miss, 403 avec body `forbidden` constant. Admin bypass. |
| `require_role(UserRole.ADMIN)` | ✅ Existe | `middleware.py:115`. Dépendance FastAPI standard utilisée par `users/router.py:173,303`. |
| `ParentChildLink` | ✅ Existe | `models.py:352`. Composite PK `(parent_pseudo, child_pseudo)`, `ondelete="CASCADE"`. Table `parent_child_links`. |
| `Evaluation.status` (Enum) | ✅ Existe | Mappé via `Enum(EvaluationStatus, name="evaluation_status_enum", native_enum=False)`. |
| Convention test cross-tenant (s17, s14) | ✅ Existe | `tests/api/test_users_parent_child.py:144-181` seed `seeded_admin`, `seeded_parent`, `seeded_eleve`, `seeded_another_parent`. `_bearer(user)` retourne le header. |

### Pas de dérive bloquante

Toutes les briques existent et sont alignées avec l'ADR 005 (RBAC) et ADR
013 (deux-state status). **Pas de drift dans le périmètre** : la story est
un complément pur de s18, pas une refonte.

### Drifts non-bloquants à noter en plan

**Drift 1 — Le `EvaluationService.upload` n'a pas de méthode `score_manual`.**
La story ajoute deux opérations (update + reprocess) qui n'existent pas
encore. Le plan doit ajouter deux méthodes au service (et les tester
séparément) plutôt que de les inliner dans le router (violation de la
séparation router/service imposée par AGENTS.md).

**Drift 2 — Le reprocess doit recharger l'image depuis S3.** Pas d'inline
octet-by-octet dans le router. Le service doit offrir un
`reprocess(evaluation_id)` qui : charge la ligne par id, télécharge
`get_object(s3_key)`, écrit un tempfile, appelle `extractor.extract(...)`,
met à jour la ligne avec le nouveau `ExtractionResult`, supprime le
tempfile. Même pattern que `upload` mais en mode update.

**Drift 3 — L'AC2 demande 409 si l'évaluation n'est PAS en
`manual_review_needed`.** Le service doit raise une erreur contrôlée
(`EvaluationError` ou une nouvelle `EvaluationStateError`) que le router
mappe à 409. La mapping table du router s18 (415/413/422/500) doit
gagner un cas 409.

**Drift 4 — Le router s18 a un seul fichier.** Les agentic notes
suggèrent `score_manual.py` + `reprocess.py` séparés. La convention
existante (un seul `router.py` par sous-domaine) penche pour l'ajout
des deux endpoints au router existant, mais c'est un choix d'équipe —
à trancher en plan (pas un blocker, légère dette de cohérence).

## Fichiers réellement impliqués

### Backend (création)

- `backend/app/api/evaluations/schemas.py` — **modifié** (ajout
  `ScoreManualRequest`, `ScoreManualResponse`, `ReprocessResponse`,
  `EvaluationErrorResponse` pour le 409). L'extension est minime (les
  schémas s18 restent).
- `backend/app/services/ocr/evaluation_extractor.py` — **modifié**
  (ajout `score_manual(evaluation_id, ...)` et `reprocess(evaluation_id)`
  sur `EvaluationService`, + un `EvaluationStateError` pour le 409).
  Aucune modification de l'extracteur.
- `backend/app/api/evaluations/router.py` — **modifié** (ajout des deux
  endpoints + mapping table étendue pour 409).
- `backend/app/api/evaluations/factory.py` — **modifié** marginalement
  (les nouveaux endpoints partagent la même dépendance que `upload` —
  pas de nouvelle DI si la signature du service reste compatible).

### Tests (création)

- `backend/tests/api/test_evaluations.py` — **étendu** (ajout des tests
  AC1-AC8 + 2 tests bite-defence pour la transition
  `manual_review_needed → scored` + cross-tenant bite déjà couvert par
  AC8). Le fichier existe déjà (s18) et gagne une section
  `s18b-` au-dessus. Alternative : nouveau fichier
  `tests/api/test_evaluations_admin.py` pour isoler les tests s18b —
  à trancher en plan.

### ADR (création)

- `docs/decisions/014-evaluation-admin-and-parent-actions.md` — consigne
  que **les deux endpoints sont admin-first avec une exception
  parent-lié**, et que la transition d'état se fait au service layer
  (pas de mutation directe dans le router).

Pas de nouvel ADR pour la séparation router/fichiers (Drift 4) — c'est
un choix de cohérence interne, pas une décision structurelle.

### Frontend (hors périmètre)

**La story n'a pas de frontend.** L'AC2 mentionne "le frontend banner
s18" — c'est une autre story (probablement s20 ou s23). Les
agentic notes ne mentionnent aucun fichier frontend.

Conséquence : **on n'invoque pas `/ks-design`**. La prochaine étape est
`/ks-plan s18b`.

## Stratégie d'implémentation (recommandée)

### Architecture

```
HTTP (POST /api/evaluations/{id}/score-manual)
   │
   ▼
EvaluationRouter.score_manual(id, body, user, db)
   │
   ├─ RBAC gate ─────────────────────────────────────────┐
   │  • admin → bypass                                   │
   │  • parent → assert_parent_linked_to_child_or_403   │
   │    (claimed = row.student_pseudo)                   │
   │  • eleve  → 403                                     │
   │                                                     │
   ▼                                                     │
EvaluationService.score_manual(evaluation_id, ...)       │
   │                                                     │
   ├─ SELECT * FROM evaluations WHERE id = ?             │
   ├─ 404 si absent                                      │
   ├─ 409 si status != MANUAL_REVIEW_NEEDED  ───────────►│
   ├─ Validation des bornes (score ≥ 0, ≤ max_score)     │
   ├─ UPDATE evaluations SET status=SCORED, score=?, ...  │
   ├─ loguru.info("security.evaluation_manual_score" ...) │
   └─ retourne l'Evaluation mise à jour                  │
                                                        │
HTTP (POST /api/evaluations/{id}/reprocess)              │
   │                                                     │
   ▼                                                     │
EvaluationRouter.reprocess(id, user, db)                 │
   │                                                     │
   ├─ RBAC : admin only (require_role(UserRole.ADMIN))   │
   │                                                     │
   ▼                                                     │
EvaluationService.reprocess(evaluation_id)               │
   │                                                     │
   ├─ SELECT la ligne par id                             │
   ├─ 404 si absent                                      │
   ├─ refuse si status == SCORED (409 — déjà scorée)     │
   │   (AC dit "reprocess un MANUAL_REVIEW_NEEDED";      │
   │   re-scorer une copie déjà scorée n'a pas de sens)  │
   ├─ bytes = s3.get_object(row.s3_key)                  │
   ├─ tempfile, call extractor.extract(tmp_path)         │
   ├─ UPDATE evaluations SET status=?, score=?, ...      │
   │   (status=SCORED si nouveau score, sinon MANUAL)    │
   ├─ supprime le tempfile (finally)                     │
   └─ retourne le nouveau ExtractionResult               │
```

### Pourquoi ne pas faire la mutation directement dans le router ?

Trois raisons (alignement avec AGENTS.md § Backend) :

1. **Séparation router/service** : les routers délèguent, les services
   contiennent la logique métier. L'AC5 ("les deux endpoints mettent à
   jour status") est une règle métier — pas un détail HTTP.
2. **Testabilité** : tester `EvaluationService.score_manual` à un
   niveau service ne nécessite pas de monter un `TestClient` FastAPI ni
   de stubber le middleware JWT. Test direct du service.
3. **Réutilisabilité** : si un autre canal (CLI admin, batch) doit
   un jour scorer manuellement, il appelle la même méthode de service.

### Pourquoi limiter le reprocess aux `MANUAL_REVIEW_NEEDED` ?

- L'AC4 dit "re-invokes the LLM vision extractor on the original image"
  — l'usage pédagogique est : la copie n'a PAS été scorée
  automatiquement, l'admin force un retry.
- Re-scorer une copie déjà scorée ouvre la porte à des écarts
  (l'admin re-tente, le LLM retourne un score différent, l'élève
  conteste) — c'est une feature de "reprocess after model upgrade"
  (s23+) et pas de la s18b.
- Story dit "reprocess renvoie un nouveau résultat (ou
  `manual_review_needed` si toujours KO)" — le 200 attend du contenu
  ; si l'AC4 n'interdit pas le reprocess d'une SCORED, le semantique
  est ambigu. **Recommandation : 409 sur SCORED, on lèvera la
  restriction en s23 si besoin.**

### Pourquoi un nouvel `EvaluationStateError` plutôt qu'étendre `EvaluationError` ?

L'enum `EvaluationErrorKind` a trois valeurs (`INVALID_FILE`,
`STORAGE_FAILURE`, `EXTRACTION_FAILURE`) — toutes liées à l'**upload**.
Le 409 est un problème de **state transition** : orthogonal à l'upload.
Ajouter une valeur `STATE_CONFLICT` pollue l'enum avec un cas qui
n'a rien à voir avec le reste. Plus propre : un
`EvaluationStateError(message)` dédié, mappé à 409 dans le router.

## Pièges identifiés

1. **Piège 1 — Validation des bornes `score` et `max_score`.** L'AC
   agentic note piège : "score ≥ 0, max_score ≥ 0, score ≤ max_score".
   La validation se fait **avant** la persistance. Si elle échoue :
   422 (validation Pydantic via le body schema) — pas 409. La frontière
   est nette : 422 = payload invalide, 409 = état métier invalide.

2. **Piège 2 — Isolation multi-tenant pour le parent.** L'AC3 dit
   "non-admin, non-parent lié → 403". L'AC8 dit "un parent ne peut
   pas scorer une évaluation d'un enfant non lié". Le helper
   `assert_parent_linked_to_child_or_403(user, claimed, route, db)`
   fait exactement ça : il résout le `student_pseudo` de la ligne
   `Evaluation`, puis vérifie le lien parent/enfant. Le test AC8 :
   seed `seeded_parent` (P), `seeded_eleve_alice` (A, P→A lié),
   `seeded_eleve_bob` (B, pas lié) ; seed une `Evaluation` row pour
   B ; POST avec le JWT de P → 403. AC8 couvert.

3. **Piège 3 — Le reprocess ne supprime PAS l'historique.** Agentic
   note piège : "ne pas supprimer le résultat précédent — garder
   l'historique". Le modèle `Evaluation` n'a pas de colonne historique
   (pas de `previous_score`, `previous_teacher_comments`, etc.).
   Solution : **on n'écrit pas l'historique en base** dans s18b, mais
   on logge chaque reprocess dans loguru avec
   `evaluation.reprocess_attempted` (pseudo, evaluation_id,
   previous_status, new_status, new_score) — l'audit reste disponible
   via les logs. Ajouter une colonne d'historique est une dette à
   trancher en s23 (model evolution). Le piège est ainsi désamorcé
   par les logs, pas par un schéma.

4. **Piège 4 — Évaluation déjà scorée + admin tente le reprocess.**
   C'est un cas réel : admin voit une note "10/20" dans le LLM
   (status=SCORED), clique "Relancer" pour voir si la note change
   avec un modèle plus récent. **On l'interdit en s18b (409)**, on
   l'ouvrira en s23 si le besoin émerge.

5. **Piège 5 — Élève A tente de scorer sa propre copie.** L'AC3 dit
   "non-admin, non-parent lié → 403". Un élève qui tente de scorer
   sa propre copie : il n'est pas admin et n'a pas de lien
   parent-enfant avec lui-même (la s14 docstring autorise
   `claimed == user.pseudo` dans le helper parent — mais ici on
   n'appelle PAS ce helper, on appelle le RBAC strict). Le routeur
   doit donc rejeter `eleve` avec 403. **Solution** : on n'utilise
   PAS `assert_parent_linked_to_child_or_403` pour le score-manual
   (trop laxiste), on code un RBAC strict : `user.role is ADMIN`
   OR (`user.role is PARENT` AND
   `assert_parent_linked_to_child_or_403(...)`).

6. **Piège 6 — Tests d'image pour le reprocess.** Le test "le
   reprocess produit un score quand l'OCR marche" doit mocker la
   réponse LLM via `httpx.MockTransport` (cf. s18) ou via un stub
   injecté dans `EvaluationExtractor`. Le test "le reprocess échoue
   et laisse MANUAL_REVIEW_NEEDED" mock une réponse sans score.

7. **Piège 7 — Fuite de tempfile dans le reprocess.** Comme pour
   `upload`, le `tempfile.NamedTemporaryFile(delete=False)` doit
   être unlink dans un `finally`. Sinon un crash LLM laisse un
   fichier orphelin dans `/tmp` (Windows : `%TEMP%`).

8. **Piège 8 — Le `EvaluationError` mapping table grandit.** Le
   router s18 a un `_status_for_evaluation_error` qui mappe
   `INVALID_FILE`, `EXTRACTION_FAILURE`, `STORAGE_FAILURE` à 415/413/422/500.
   Le 409 est sur un nouveau type d'erreur (`EvaluationStateError`).
   Refactor : un mapping table unique `{kind_or_type: status}` au lieu
   de la fonction actuelle — sinon le router devient un
   `if/elif` à rallonge. Trivial mais le plan doit le mentionner.

## Complexité re-scoring

**Déclarée : 2.** Score recalibré après lecture du code : **2**.

Justification :

- **Les briques existent** : `EvaluationService` (à étendre),
  `MinioClient.get_object`, `assert_parent_linked_to_child_or_403`,
  `require_role`, `EvaluationStatus` enum, conventions de test.
- **Pas de nouveau modèle, pas de migration** : on UPDATE un row
  existant.
- **Pas de nouveau service d'infra** : on réutilise
  `EvaluationExtractor` et `MinioClient`.
- **Le piège 5 (RBAC strict) ajoute 1-2 tests bite** mais ne change
  pas la complexité.
- **Pas de Celery, pas de streaming, pas de frontend** : pure logique
  backend CRUD.

**Verdict : 2 confirmé.** Pas de split proposé. Le plan peut tenir
en 5-7 tâches (cf. estimation ci-dessous) — bien sous le seuil de 10.

## Stratégie de tests

| AC | Type de test | Localisation | Mock / fixture |
| --- | --- | --- | --- |
| AC1 (admin peut scorer) | API integration | `tests/api/test_evaluations.py` (étendu) | `seeded_admin` + `Evaluation` row seedée en DB |
| AC2 (409 si déjà scorée) | API integration | idem | `Evaluation` row en status=SCORED, POST → 409 |
| AC3 (non-admin non-parent → 403) | API integration | idem | `seeded_eleve` (alice) avec une `Evaluation` row d'alice ; POST avec JWT d'alice → 403 |
| AC4 (reprocess → 200 ou manual_review) | API integration | idem | `_OcrStub` qui retourne un score / un `manual_review_needed` |
| AC5 (status → scored on success) | API integration | idem | assertion sur la row DB après POST |
| AC6 (admin test minimal) | (recouvrement de AC1) | idem | idem AC1 |
| AC7 (non-admin test minimal) | (recouvrement de AC3) | idem | idem AC3 |
| AC8 (parent non lié → 403) | API integration | idem | `seeded_parent` (P) + `seeded_eleve_alice` (A, lié) + `seeded_eleve_bob` (B, pas lié) ; `Evaluation` row pour B ; POST avec JWT de P → 403 |

**Bite-defense supplémentaires** (au-delà des ACs explicites) :

- `test_score_manual_rejects_negative_score` (Piège 1)
- `test_score_manual_rejects_score_greater_than_max` (Piège 1)
- `test_reprocess_persists_no_history_column_change` (Piège 3 — confirme
  que la table n'est pas altérée par l'ajout)
- `test_eleve_cannot_score_own_evaluation` (Piège 5 — RBAC strict)
- `test_reprocess_leaves_manual_review_needed_on_ocr_failure` (AC4 +
  défense en profondeur)

Un test par AC conformément à AGENTS.md.

## Open questions

1. **Split du router (`score_manual.py` + `reprocess.py`) ou ajout au
   router existant ?** Les agentic notes suggèrent le split ; la
   convention du repo penche pour un seul `router.py` par sous-domaine
   (cf. `documents/router.py`, `users/router.py`). L'impact est
   uniquement de la cohérence stylistique — pas de blocker. **À
   trancher en plan.**

2. **`EvaluationStateError` vs extension de `EvaluationErrorKind` ?**
   Recommandation dans la section « Stratégie » : nouvelle classe
   pour ne pas polluer l'enum upload. Le plan peut choisir l'inverse
   (ajouter une valeur `STATE_CONFLICT` à l'enum) — pas un blocker,
   mais l'enum perd sa cohérence sémantique (3 valeurs upload + 1
   état).

3. **Doit-on permettre le reprocess sur une évaluation déjà `SCORED` ?**
   Recommandation : 409, on l'ouvre en s23. Le plan peut décider
   autrement si l'équipe a un cas d'usage concret (par exemple,
   "l'admin a corrigé manuellement et veut reverifier avec un LLM
   plus récent"). Trivial à inverser — c'est un 409 → 200.

4. **Les élèves peuvent-ils déclencher le reprocess sur leur propre
   copie ?** L'AC4 dit "admin only, JWT". La lecture stricte est :
   seul l'admin a accès. Le plan doit-il permettre à un élève de
   demander un reprocess de sa propre copie ? Lecture pragmatique :
   non — l'élève n'a pas la légitimité de contester la note
   automatiquement. Mais ce n'est pas explicite dans l'AC. **À
   trancher en plan ; recommandation : admin only, pas d'exception
   élève.**

5. **Faut-il une route `GET /api/evaluations/{id}` pour récupérer
   l'évaluation mise à jour ?** L'AC1 dit "Returns 200 with the
   updated evaluation" — donc l'endpoint retourne l'objet complet.
   Pas besoin d'un GET séparé pour s18b. Une story future (s19 ou
   s20) pourrait ajouter un GET list/détail des évaluations.

## Risques (rappel du complexity 2)

- **Piège 1 (validation des bornes)** : mitigé par Pydantic `Field(ge=0)`
  sur le body schema.
- **Piège 2 (isolation parent)** : mitigé par le helper existant
  `assert_parent_linked_to_child_or_403`.
- **Piège 5 (élève tente de scorer)** : mitigé par RBAC strict au
  routeur (ne pas appeler le helper parent qui autorise
  `claimed == user.pseudo`).
- **Reprocess échoue** : mitigé par le `try/finally` autour du
  tempfile + un UPDATE qui conserve `manual_review_needed` si
  l'extraction ne produit pas de score.
- **Latence du reprocess** : un appel HTTP synchrone au LLM
  (~50-200 ms). Acceptable pour un endpoint admin, comme l'upload
  s18.

## Décisions architecturales à enregistrer

Si le plan entérine les choix ci-dessus, créer :

- **ADR 014 — evaluation-admin-and-parent-actions** : consigne que
  les deux endpoints sont admin-first avec une exception parent-lié
  (score-manual uniquement), et que la transition d'état
  `MANUAL_REVIEW_NEEDED → SCORED` se fait au service layer. **Draft
  dans le plan.**

(Le séquençage exact — créer les ADRs en plan ou en execute — est
tranché par le skill `ks-plan`.)

## Annexe — fichiers lus pour cette recherche

- `docs/stories.md:906-942` (story + AC + agentic notes)
- `docs/decisions/005-auth-rs256-rbac.md` (RBAC)
- `docs/decisions/013-evaluation-status-enum-dedie.md` (justification
  des deux états)
- `backend/app/core/database/models.py:25-45` (EvaluationStatus enum)
- `backend/app/core/database/models.py:225-290` (Evaluation model)
- `backend/app/core/database/models.py:352-402` (ParentChildLink)
- `backend/app/core/auth/middleware.py:67-285` (auth helpers, parent
  link)
- `backend/app/api/evaluations/router.py` (entier, s18)
- `backend/app/api/evaluations/schemas.py` (entier, s18)
- `backend/app/api/evaluations/factory.py` (entier, s18)
- `backend/app/services/ocr/evaluation_extractor.py` (entier, s18)
- `backend/app/services/storage/minio_client.py:40-80` (S3 client
  methods)
- `backend/tests/api/test_evaluations.py:1-200` (s18 test fixtures)
- `backend/tests/api/test_users_parent_child.py:144-200` (cross-tenant
  fixture pattern)

## Conclusion

Prémisse vérifiée : toutes les briques existent (modèle, service,
extracteur, S3 client, helpers RBAC, fixtures de test). Aucun drift
majeur. Le scope est bien défini et raisonnable pour une story de
complexité 2.

Les choix à faire en plan sont stylistiques (router split vs unifié,
classe d'erreur séparée vs extension d'enum) ou fonctionnels mineurs
(reprocess d'une SCORED, élève déclencheur). Ils n'affectent ni
l'architecture ni les briques existantes.

**Recherche terminée. Aucun blocage.**
