---
id: s18-uploader-copie-extraire-score
title: "Recherche — Téléverser une copie d'évaluation corrigée et extraire le score"
status: done
---

# s18 — Recherche

## Story

`docs/stories.md:867` — **s18-uploader-copie-extraire-score — Téléverser une
copie d'évaluation corrigée et extraire le score.**

- **As an** élève
- **I want** téléverser une photo de ma copie d'évaluation corrigée par
  l'enseignant
- **so that** le système extraie le score et les annotations.

**Complexité déclarée** : 4 — LLM vision + extraction de score (regex + LLM) +
stockage structuré + edge cases.

**Dépendances** : s10 (upload API), s15 (auth). Les deux sont livrées.

## Acceptance criteria (verbatim depuis stories.md)

1. `POST /api/evaluations/upload` accepte `multipart/form-data` avec `pseudo`,
   `subject` et `file` (image).
2. La vision LLM extrait : `score` (number | "non précisé"), `max_score` (number
   | "non précisé"), `annotations` (list[str]), `teacher_comments` (str | null).
3. L'extraction utilise À LA FOIS une regex (pour les scores explicites comme
   "12/20") ET un appel LLM (pour les commentaires non structurés).
4. Si ni la regex ni le LLM ne trouve de score, le système renvoie l'upload
   avec `status: "manual_review_needed"` et indique à l'utilisateur (ou un
   admin) de saisir le score manuellement (la saisie manuelle est s18b).
5. Les données extraites sont persistées dans une ligne `Evaluation` en
   PostgreSQL.
6. Un test avec une image contenant "12/20" vérifie que la regex le capte.
7. Un test avec une image (sans score clair) vérifie que le LLM est appelé et
   qu'un résultat est renvoyé (ou `manual_review_needed`).
8. Un test vérifie l'isolation multi-tenant.

## Localisation de la vérité

L'agent a lu le code dans le worktree
`C:\Workspace\ktutor\.worktrees\s18-uploader-copie-extraire-score`
(branche `feature/s18-uploader-copie-extraire-score`, HEAD 46ad4bc, propre).
Toute la cartographie qui suit provient de cette lecture.

## Prémisse vérifiée (vs dérive du code)

| Fichier / élément attendu | Statut | Note |
| --- | --- | --- |
| `app/services/ocr/evaluation_extractor.py` | **À créer** | N'existe pas. Le seul module `ocr` est `app/services/rag/ocr.py` (livré s01). |
| `app/api/evaluations/router.py` | **À créer** | Aucun dossier `app/api/evaluations/` n'existe. Les routers actuels : `auth`, `chat`, `dashboard`, `documents`, `users`. |
| `Evaluation` model dans `models.py` | **À créer** | Modèles actuels : `User`, `ParentChildLink`, `Document`, `Exercise`, `Attempt`. Aucun modèle évaluation. |
| `MultimodalOcr` réutilisable | ✅ Existe | `app/services/rag/ocr.py:57`. Parle à DeepSeek-OCR-2 via `httpx` (ADR 008). `MockTransport` pour les tests. |
| Convention S3 multi-tenant | ✅ Existe | `MinioClient.put_object` retourne `students/<pseudo>/<document_id>` (cf. ADR 009). |
| Helpers RBAC | ✅ Existent | `require_role`, `get_current_user`, `assert_jwt_pseudo_matches_or_403`, `assert_parent_linked_to_child_or_403` dans `app/core/auth/middleware.py`. |
| LLM client pour l'extraction de score | ⚠️ Drift | `app/services/llm/client.py` est **chat-only** (OpenAI-compat). Pour l'extraction de score depuis une image on ne peut pas l'utiliser directement — on parle à `MultimodalOcr` (qui prend l'image + un prompt custom). |
| Enum `MANUAL_REVIEW_NEEDED` | ✅ Existe | `DocumentStatus.MANUAL_REVIEW_NEEDED` (`models.py:23`). On l'inspire pour l'enum `EvaluationStatus`. |
| Convention de tests cross-tenant | ✅ Existe | `test_documents.py:705`, `test_parent.py:390`, etc. Fixtures `rsa_keypair` + `_point_settings` + `db_engine` + `client` + `_bearer`. |

### Drifts critiques à corriger en plan

**Drift 1 — AC1 mentionne `pseudo` dans le body, mais s15 l'interdit.**

`app/api/documents/router.py:131-156` rejette explicitement le champ `pseudo`
du multipart depuis s15. Le router s18 doit faire la même chose :
l'identité vient du JWT, pas du body. Le plan doit :

- accepter `subject` et `file` uniquement ;
- rejeter `Form(pseudo)` (defense in depth) avec 422 + `value_error.extra` ;
- aligner l'AC1 sur la convention s15 (override documenté).

**Drift 2 — `LlmClient` n'est pas multimodal.**

L'AC3 dit « regex + LLM call ». L'interprétation littérale suggère deux
appels : un LLM multimodal (vision) qui transcrit l'image, puis un LLM chat
qui extrait le score depuis la transcription. Mais l'ADR 008 montre que
`MultimodalOcr` peut déjà recevoir un **prompt custom** (`_build_prompt` /
`_build_strict_prompt` dans `ocr.py:107-120`) et renvoie du JSON strict.

La voie la plus simple (et la plus testable) :

- `MultimodalOcr.transcribe_image(path, prompt=...)` est **étendu** pour
  accepter un prompt custom (refactor minimal, voir Piège 1) ;
- OU on crée `EvaluationExtractor` qui **possède** sa propre instance
  `MultimodalOcr` et l'appelle avec un prompt d'extraction de score.

La deuxième voie est plus propre (le prompt par défaut reste générique ;
`EvaluationExtractor` injecte le sien). **Recommandation : voie 2** —
c'est ce que la planifiera.

**Drift 3 — Le service de récompenses n'existe pas.**

`CLAUDE.md` mentionne 10 points pour l'upload d'une copie corrigée. Le
service `app/services/rewards/` n'existe pas (vérifié : seuls
`agents/`, `correction/`, `dashboard/`, `exercises/`, `llm/`, `rag/`,
`storage/` existent). Pour s18, on **n'implémente pas la gamification**.
Le suivi des récompenses est hors périmètre ; une story ultérieure
(peut-être s20 ou s23) le couvrira.

## Fichiers réellement impliqués

### Backend (création)

- `backend/app/services/ocr/__init__.py` — nouveau package
- `backend/app/services/ocr/evaluation_extractor.py` — service
  d'extraction de score (regex sur le texte OCR + appel LLM multimodal
  avec prompt custom)
- `backend/app/api/evaluations/__init__.py` — nouveau package
- `backend/app/api/evaluations/router.py` — `POST /api/evaluations/upload`
- `backend/app/api/evaluations/schemas.py` — Pydantic request/response
- `backend/app/api/evaluations/factory.py` — wiring DI (mirror de
  `documents/factory.py`)

### Backend (modification)

- `backend/app/core/database/models.py` — ajout de `Evaluation` model +
  enum `EvaluationStatus` (states: `scored`, `manual_review_needed`).
  `init_db()` applique la metadata via `Base.metadata.create_all`, donc
  pas de migration Alembic nécessaire (convention `models.py:166`).
- `backend/app/main.py` — `include_router` du router `evaluations`.
- `backend/app/core/config.py` — éventuellement `evaluation_max_*` seuils
  (taille d'image, max caractères pour `teacher_comments`). **À voir en
  plan** : on peut s'aligner sur `max_upload_size_mb=20` sans nouveau
  setting.

### Tests (création)

- `backend/tests/services/ocr/__init__.py` — package
- `backend/tests/services/ocr/test_evaluation_extractor.py` — tests
  unitaires du service (regex, prompt LLM, fallback `manual_review_needed`)
- `backend/tests/api/test_evaluations.py` — tests d'intégration
  (RBAC, multipart, cross-tenant, drift `Form(pseudo)` rejeté)

### Frontend (hors périmètre)

**La story n'a pas de frontend.** Les agentic notes citent uniquement des
fichiers backend. Le dashboard élève qui *affichera* les scores extraits
est livré par une story postérieure (probablement s20 ou s23 — vérifier
l'ordre dans `docs/stories.md`).

Conséquence : **on n'invoque pas `/ks-design`**. La prochaine étape est
`/ks-plan s18`.

## Stratégie d'extraction de score (recommandée)

### Architecture

```
HTTP (POST /api/evaluations/upload)
   │
   ▼
EvaluationService (services/ocr/evaluation_extractor.py)
   │
   ├─ S3 put (via MinioClient)   →  students/<pseudo>/<id>.<ext>
   │
   ├─ OCR multimodal              →  MultimodalOcr avec prompt custom
   │  (vision LLM, ADR 008)
   │
   ├─ Regex sur le texte OCR      →  SCORE_RE = r"\b(\d+)\s*/\s*(\d+)\b"
   │  (fast path, 0 appel LLM)
   │
   ├─ Si regex rate :
   │   └─ LLM "structuration"     →  même appel OCR avec prompt
   │      (déjà multimodal, on lui
   │      demande un JSON structuré)
   │
   └─ Persist Evaluation row      →  status=scored | manual_review_needed
```

### Stratégie d'appel OCR

L'ADR 008 confirme que `MultimodalOcr` accepte un prompt custom. La voie
la moins intrusive :

- `EvaluationExtractor` instancie **son propre** `MultimodalOcr` (mêmes
  settings `deepseek_ocr_url` / `deepseek_ocr_timeout`).
- Il l'appelle avec un prompt dédié : « Renvoie UNIQUEMENT ce JSON :
  `{"score": number|null, "max_score": number|null, "annotations":
  [string], "teacher_comments": string|null, "ocr_text": string} ».

Le service parse la réponse JSON, tente d'abord la regex sur `ocr_text`
(pour les cas évidents), et fallback sur le JSON multimodal pour les
cas ambigus. Si les deux échouent → `manual_review_needed`.

### Pourquoi ne pas séparer OCR + LLM chat ?

Parce que ça double le coût et la latence pour zéro gain. Le LLM
multimodal (DeepSeek-OCR-2) fait déjà l'OCR **et** la structuration en
un seul appel. Le `LlmClient` chat serait pertinent pour une *deuxième
passe* de raisonnement, mais l'AC3 (« regex pour les scores explicites »)
ne le demande pas — la regex est le fast path, le LLM multimodal est le
slow path.

## Pièges identifiés

1. **Piège 1 — `MultimodalOcr.transcribe_image` n'accepte pas de prompt
   custom.** L'API actuelle utilise un prompt codé en dur
   (`_build_prompt` dans `ocr.py:107`). Solution : ne pas modifier
   `MultimodalOcr` (risque de régression sur s10). `EvaluationExtractor`
   possède sa propre instance et parle **directement** au service
   DeepSeek-OCR-2 via `httpx` (en réutilisant `LOW_CONFIDENCE_THRESHOLD`
   et la même logique de retry + JSON parsing). C'est une duplication
   minimale mais qui isole le risque.

   *Alternative* : ajouter un paramètre `prompt: str | None = None` à
   `transcribe_image`. Refactor de 3 lignes dans `ocr.py`, test
   d'existant à valider. Décision finale en plan.

2. **Piège 2 — L'AC1 demande `pseudo` dans le body.** Cf. Drift 1. Le
   plan doit overrider l'AC pour aligner sur s15.

3. **Piège 3 — Hallucination de score par le LLM.** L'agentic note le
   souligne (story `§ Traps`). Le prompt doit inclure explicitement
   « Si aucun score n'est lisible, ne devine pas — réponds
   `"score": null` ». Le test AC6 (image "12/20") et le test AC7
   (image sans score) couvrent les deux branches.

4. **Piège 4 — Extraction de la mauvaise note.** Ex : « élève noté 12
   sur 20 » dans une consigne, mais la vraie note est 8. La regex
   `\b(\d+)\s*/\s*(\d+)\b` n'ancre que les patterns avec `/`. Pour
   « note : 12/20 » elle matche, pour « l'élève a 12 ans » elle ne
   matche pas (pas de `/`). C'est l'**intention** de l'agentic note.
   Le test AC7 doit utiliser une image avec « 12/20 » écrit **en gros
   au-dessus de la copie** (zone typique de l'enseignant) — pas dans
   le corps du texte.

5. **Piège 5 — Image illisible.** L'agentic note le prévoit : « A
   photo with low resolution or bad lighting may yield no text — fall
   back to manual_review_needed without retrying the LLM. » Le
   `MultimodalOcr` retourne `OcrResult(ok=False, reason=...)` dans ce
   cas. `EvaluationExtractor` doit traiter `ok=False` comme
   `manual_review_needed` sans second appel.

6. **Piège 6 — Tests d'image.** Le test AC6 doit écrire « 12/20 » sur
   une image PIL pour être reproductible (pas de dépendance à un fichier
   binaire). Le test AC7 doit utiliser une image sans texte (image
   blanche ou photo abstraite). Tous deux mockent la réponse HTTP via
   `httpx.MockTransport` (cf. convention `test_ocr.py:23`), donc
   l'image réelle n'a pas besoin d'être lisible par un vrai modèle.

7. **Piège 7 — Multi-tenant pour les images.** Comme `Document`,
   `Evaluation` doit avoir `student_pseudo` FK CASCADE. Le test
   cross-tenant doit vérifier qu'un élève A ne peut pas GET une
   évaluation de B (mais ce GET est hors scope s18 — s18b ?). Le test
   cross-tenant pertinent pour s18 : un élève A ne peut pas **uploader
   en usurpant** le pseudo de B. Comme on lit le pseudo du JWT
   uniquement, ce test se réduit à vérifier que `Form(pseudo)` est
   rejeté (déjà couvert par Drift 1).

## Complexité re-scoring

**Déclarée : 4.** Score recalibré après lecture du code : **3-4**.

Justification :

- **L'OcrResult multimodal + JSON parsing existe** (s01). Pas de dette
  sur la partie OCR.
- **Le pattern multipart + factory + router existe** (s10). On copie
  avec adaptations.
- **Le pattern d'erreur `MANUAL_REVIEW_NEEDED` + persistance `Document`
  row** existe. On transpose au modèle `Evaluation`.
- **Le LLM multimodal avec prompt custom** est la partie nouvelle. Pas
  triviale mais bien encadrée par l'ADR 008.
- **Le test cross-tenant** est plus simple que pour `documents` parce
  qu'il n'y a pas de ChromaDB à isoler.

**Recommandation : 3-4, garder à 4 par sécurité** (le edge case
manuscrit illisible + le LLM qui hallucine sont des pièges réels). Pas
besoin de split (s18b existe déjà dans stories.md pour la saisie
manuelle).

## Stratégie de tests

| AC | Type de test | Localisation | Mock |
| --- | --- | --- | --- |
| AC1 (multipart + drift `Form(pseudo)` rejeté) | API integration | `tests/api/test_evaluations.py` | `httpx.MockTransport` + `dependency_overrides` |
| AC2 (champs extraits) | Service unit | `tests/services/ocr/test_evaluation_extractor.py` | `httpx.MockTransport` |
| AC3 (regex + LLM fallback) | Service unit | idem | mock réponse JSON + `re.search` |
| AC4 (manual_review_needed) | Service unit | idem | mock réponse sans score |
| AC5 (persistance Evaluation row) | API integration | `tests/api/test_evaluations.py` | `db_engine` SQLite mémoire |
| AC6 (regex "12/20") | Service unit | idem | mock réponse `ocr_text="Note: 12/20"` |
| AC7 (LLM sans score clair) | Service unit | idem | mock réponse `{"score": null, ...}` |
| AC8 (multi-tenant) | API integration | `tests/api/test_evaluations.py` | deux élèves A et B, A upload, B ne peut pas voir |

Un test par AC, conformément à AGENTS.md.

## Open questions

1. **Refactor `MultimodalOcr.transcribe_image(prompt=...)` ou duplication
   dans `EvaluationExtractor` ?** Le refactor est 3 lignes mais impacte
   s10. La duplication est plus sûre. **Recommandation :
   duplication**. Décision finale en plan.

2. **Faut-il un endpoint `GET /api/evaluations` pour l'AC5 ?** L'AC5
   dit « persistance en PostgreSQL » mais ne demande pas de GET. La
   consultation est probablement dans une story ultérieure (s20 ?).
   **Recommandation : pas de GET dans s18**, on persiste uniquement.

3. **L'AC1 demande `pseudo` dans le body — drift s15.** Faut-il
   corriger la story (`docs/stories.md`) en même temps que le plan, ou
   documenter le drift dans le plan et corriger la story après ? Le
   pipeline bloque-t-il ? **Recommandation : overrider dans le plan
   avec justification explicite**, ne pas toucher `stories.md` (le
   drift est documenté ici).

4. **Status enum** : `EvaluationStatus` doit-il être `{scored,
   manual_review_needed, error}` ou réutiliser `DocumentStatus` ?
   Réponse : enum dédié. `DocumentStatus.ERROR` n'a pas de sens ici
   (la copie est valide même si le score est absent).

## Risques (rappel du complexity 4)

- **Hallucination LLM** : mitigée par le prompt strict + le test AC7.
- **Manuscrit illisible** : mitigé par `OcrResult.ok=False` →
  `manual_review_needed` (Piège 5).
- **Extraction de la mauvaise note** : mitigée par la regex ancrée sur
  `/` (Piège 4).
- **Latence OCR** : un appel HTTP synchrone par upload. Acquis pour
  s18 (pas de Celery ici — ADR 010 ne couvre que le chat streaming).
  Une story future pourra async-ifier.

## Décisions architecturales à enregistrer

Si le plan entérine les choix ci-dessus, créer :

- **ADR 012 — evaluation-ocr-via-multimodal-llm** : consigne que
  `EvaluationExtractor` réutilise `MultimodalOcr` avec un prompt custom
  plutôt que d'ajouter une seconde chaîne OCR. **Draft dans le plan**.
- **ADR 013 — evaluation-status-enum-dedie** : `EvaluationStatus` est
  un enum séparé de `DocumentStatus` (`scored`, `manual_review_needed`).
  **Draft dans le plan**.

(Le séquençage exact — créer les ADRs en plan ou en execute — est
tranché par le skill `ks-plan`.)

## Annexe — fichiers lus pour cette recherche

- `docs/stories.md:867-902` (story + AC + agentic notes)
- `docs/decisions/008-deepseek-ocr-2-for-vision.md` (ADR 008 complet)
- `docs/decisions/005-auth-rs256-rbac.md` (RBAC + isolation)
- `docs/decisions/009-seaweedfs.md` (mention ADR 009 pour S3)
- `docs/architecture.md` (référence stack — non relu intégralement,
  conventions extraites des ADR)
- `backend/app/main.py` (mount points)
- `backend/app/core/config.py` (settings — complet)
- `backend/app/core/database/models.py` (models existants — complet)
- `backend/app/core/auth/middleware.py` (helpers RBAC — header)
- `backend/app/services/rag/ocr.py` (MultimodalOcr — complet)
- `backend/app/services/rag/upload_service.py` (pattern service — partiel)
- `backend/app/services/storage/minio_client.py` (S3 multi-tenant — header)
- `backend/app/services/llm/client.py` (chat-only — complet)
- `backend/app/api/documents/router.py` (pattern multipart — complet)
- `backend/app/api/documents/factory.py` (wiring DI — complet)
- `backend/app/api/dashboard/parent.py` (pattern RBAC — header)
- `backend/tests/api/dashboard/test_parent.py` (fixtures test — header)
- `backend/tests/services/rag/test_ocr.py` (MockTransport — header)

## Conclusion

Prémisse vérifiée : tous les modules auxiliaires existent
(`MultimodalOcr`, S3 multi-tenant, helpers RBAC, conventions de tests).
Le scope est bien défini et raisonnable pour une story de complexité 4.
Trois drifts à corriger dans le plan (notamment l'AC1 qui demande
`pseudo` dans le body, contrevenant à la convention s15).

**Recherche terminée. Aucun blocage.**
