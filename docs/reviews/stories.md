# Review — Story Breakdown

> Revu par : sous-agent `stories-reviewer` (contexte frais).
> Date : 2026-09-02 (re-review après étoffement de s11c-frontend-upload)
> Source : `docs/stories.md` vs `docs/prd.md`

## Note méthodologique

Le PRD ne contient pas une table littérale « Replicated (core loop) » ni une section « Explicitly NOT replicated ». La skill `stories-review` mentionne ces noms exacts. Le sous-agent utilise `Périmètre (in)` et `Hors-scope (out)` comme équivalents, comme lors des reviews précédentes. Les « Métriques de succès » du PRD sont des cibles à mesurer, pas des features à shipper — elles ne mappent pas à des stories.

## 1. Couverture du périmètre (Périmètre in)

| Périmètre PRD (in) | Story(s) | OK ? |
|---|---|---|
| Upload de documents (PDF, images dactylo, manuscrites OCR LLM) | s01, s10, s11c (maintenant fleshed out) | OK |
| Pipeline RAG par matière (collection par matière × élève) | s01, s05 | OK |
| Chat RAG (réponse sourcée de l'agent) | s02, s05, s09, s11b, s19 | OK |
| Génération d'exercices (QCM, problème, rédaction, flashcards) | s03, s06, s06b | OK |
| Correction progressive (QCM tout-ou-rien, rédaction appréciation LLM, 3 tentatives max) | s04, s07, s08, s20 | OK |
| Évaluations (upload copie corrigée → extraction score + annotations) | s18, s18b | OK |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s01, s10, s15 + tests d'isolation dans toutes les stories API | OK |
| Authentification & RBAC (JWT RS256, admin/parent/élève, identifiés par pseudo) | s12, s13, s13b, s15 | OK |
| Dashboards (progression élève, vue parent lecture seule) | s16, s17 | OK |
| i18n (FR par défaut, EN, next-intl) | s11a (scaffold), s11b (chat ns), s11c (upload ns), s21 (consolidation) | OK |
| Accessibilité (responsive smartphone/tablette, WCAG 2.1 A) | s11a (scaffold), s11b (chat a11y), s11c (upload a11y), s22 (audit) | OK |
| Observabilité (logs structurés, OTel, Prometheus, alerting) | s23, s24 | OK |

- [x] Chaque feature du périmètre est livrée par au moins une story. Périmètre complet.

## 2. Graveyard leak check (Hors-scope out)

| Item | Story qui le réintroduit | Verdict |
|---|---|---|
| RGPD / CNIL | aucune | OK |
| Déploiement cloud / production | aucune | OK |
| Paiements / abonnements | aucune | OK |
| Rôle enseignant | aucune | OK |
| Intégrations tierces (ENT, SI externes) | aucune | OK |
| App mobile native | aucune (s11c `<FileUpload>` capture caméra est `capture="environment"` HTML5, conforme PRD) | OK |
| Notifications push / email | s25 explicitement in-app | OK |
| Multi-langues au-delà de FR/EN | s21 limité à FR/EN | OK |

- [x] Aucune story ne réintroduit un item du graveyard.

## 3. Technical-layer check

Toutes les stories sont des slices end-to-end avec valeur utilisateur (CLI command, page, endpoint). Aucune story « set up the database » ou « create the API layer » isolée. Les modèles SQLAlchemy sont créés *à l'intérieur* de la story qui en a besoin (s01, s03, s04, s12, s14, s18, s20, s25).

- [x] Aucune story n'est une couche technique seule.

## 4. AC testability check (focus s11c)

| s11c AC | Testable ? | Comment |
|---|---|---|
| AC1 (page rend avec sélecteur matière, FileUpload, bouton Envoyer, i18n) | oui | Playwright DOM + i18n check |
| AC2 (FileUpload : click picker, drag & drop, mobile camera capture) | oui | Playwright + `setInputFiles` + drag simulation + viewport ≤ 768px |
| AC3 (drag styling : onDragOver → primary border, onDrop → consume event) | oui | Playwright drag + CSS assertion |
| AC4 (file card avec icône, nom, taille formatée MB, bouton Retirer) | oui | Playwright DOM + `Intl.NumberFormat` |
| AC5 (bouton Envoyer désactivé, aria-disabled, tabindex) | oui | Playwright + ARIA |
| AC6 (POST multipart via apiClient, FormData 3 champs) | oui | Playwright `page.route` request body inspection |
| AC7 (spinner pendant upload, drop zone désactivée) | oui | Playwright + CSS state |
| AC8 (201 indexed → success card avec chunks count) | oui | Playwright stub 201 |
| AC8 (201 manual_review_needed → warning card OCR) | oui | Playwright stub 201 |
| AC9a (413 → message « Fichier trop volumineux ») | oui | Playwright stub 413 |
| AC9b (415 → message « Extension non supportée ») | oui | Playwright stub 415 |
| AC9c (422 invalid_pseudo → message reload) | oui | Playwright stub 422 |
| AC9d (422 ocr_failure → message OCR échoué) | oui | Playwright stub 422 |
| AC9e (500 storage_failure → message erreur serveur) | oui | Playwright stub 500 |
| AC10 (erreur réseau → message inline Réessayer) | oui | Playwright abort/timeout |
| AC11 (aucun pseudo → label warning + aria-invalid) | oui | Playwright clear cookie |
| AC12 (uploadStore Zustand state) | oui | Test unitaire |
| AC13 (responsive 360/768) | oui | Playwright viewports |
| AC14 (axe-core 0 critical/serious + Lighthouse ≥ 90) | oui | CI job |
| AC15 (≥ 4 tests e2e) | oui | Playwright |
| AC16 (lint/typecheck/build/test exit 0) | oui | CI job |
| AC17 (commentaire head uploadStore référence s10) | grep | statique |

Toutes les ACs de s11c sont vérifiables. Le mapping `code → UI state` dans AC9 couvre tous les `UploadErrorResponse.code` du contrat s10 (`invalid_file` → 413/415, `invalid_pseudo` → 422, `ocr_failure` → 422, `storage_failure` → 500), plus le cas erreur réseau.

**Couverture des 8 états UI du contrat s10** :
- 201 indexed → AC8 ✅
- 201 manual_review_needed → AC8 (second cas) ✅
- 413 → AC9a ✅
- 415 → AC9b ✅
- 422 invalid_pseudo → AC9c ✅
- 422 ocr_failure → AC9d ✅
- 500 storage_failure → AC9e ✅
- Network error → AC10 ✅

Les 8 états UI sont couverts.

## 5. Dependency order

Walked all `### Dependencies` blocks top-to-bottom :

- s01 → (none) OK
- s02 → s01 OK
- s03 → s01, s02 OK
- s04 → s03 OK
- s05 → s01, s02 OK
- s06 → s01, s02 OK
- s06b → s01, s02, s03 OK
- s07 → s06 OK
- s08 → s04, s07 OK
- s09 → s02, s05 OK
- s10 → s01 OK
- s11a → s09, s10 (merged) OK
- s11b → s11a (merged `c3f1829`), s09 (merged `c5f6163`), s10 (merged `ff21046`) OK
- **s11c → s11a (merged `c3f1829`), s10 (merged `ff21046`), s01 (merged)** OK
- s12 → s01 OK
- s13 → s12 OK
- s13b → s12, s13 OK
- s14 → s12, s13, s13b OK
- s15 → s13 + all prior API OK
- s16 → s04, s07, s15 OK
- s17 → s14, s15, s16 OK
- s18 → s10, s15 OK
- s18b → s18, s14, s15 OK
- s19 → s15 OK
- s20 → s04, s07, s08, s16 OK
- **s21 → s11 (ambigu — voir Finding 3)** STALE id
- s22 → s11 (ambigu) STALE id
- s23 → all prior API OK
- s24 → s23 OK
- s25 → s18, s20 OK
- **s26 → s11 (ambigu) STALE id**

s21, s22 et s26 référencent encore l'ancien id monolithique « s11 ». Ce n'est pas un blocker d'exécution (s11a est shipped, s11b/s11c sont fleshed out), mais c'est un id obsolète. La sémantique pratique est : s21 → s11b shippé, s22 → s11b + s11c shippés, s26 → s11b + s11c + s19 (history) shippés.

## 6. Complexity scores

- s01: 3
- s02: 3
- s03: 3
- s04: 2
- s05: 3
- s06: 3
- s06b: 3
- s07: 3
- s08: 4 (risk stated — state machine combinatorial)
- s09: 3
- s10: 2
- s11a: 3 (re-scored from 5 after split)
- s11b: 3
- **s11c: 2** (justifiée — page + FileUpload étendu, pas de SSE, multipart géré par axios)
- s12: 2
- s13: 3
- s13b: 3
- s14: 2
- s15: 3
- s16: 3
- s17: 3 (risk stated)
- s18: 4 (risk stated — LLM vision non-deterministic)
- s18b: 2
- s19: 2
- s20: 3
- s21: 3 (risk stated)
- s22: 3
- s23: 3
- s24: 2
- s25: 3
- s26: 1

No 5, all 4s state their risk. La règle d'or (4 = risk stated, 5 = must split) est respectée.

## 7. ID format & uniqueness

Format `s<number>-<slug>` partout. Suffixes valides : s06b, s13b, s18b, s11a, s11b, s11c. Pas de doublon, pas de régression. L'ancien id `s12b` n'apparaît qu'en référence historique (l. 1238). Conforme à la review précédente.

## 8. s11c focus (suite à l'étoffement)

**s11c est shippable-ready** (commit `82850cb`) :
- 16 ACs, chacune testable, chacune ancrée à un comportement observable (DOM, attribut ARIA, requête HTTP multipart, code backend, message inline, test e2e).
- Dépendances vérifiées par commit hash (`c3f1829`, `ff21046`).
- Agentic notes très complètes : 12 pièges documentés (axios `Content-Type` boundary, drag & drop event preventDefault, iOS Safari limitations, MANUAL_REVIEW discriminator, `Intl.NumberFormat` digits, etc.), 4 open questions tranchées, out-of-scope explicite.
- Le commentaire de tête de `uploadStore.ts` exigé par AC17 verrouille le couplage au contrat s10.

**Contraste axios/fetch vs s11b explicitement documenté** :
- s11c Constraint (l. 568) : « **PAS de `fetch` direct** ici — c'est l'inverse de s11b (qui utilise `fetch` parce qu'axios bufferise les streams SSE). »
- s11c Trap #1 (l. 579) : « `Content-Type: multipart/form-data` ne doit PAS être mis manuellement. Si axios voit un `Content-Type` explicite avec `FormData`, il n'ajoute pas le `boundary` et le backend rejette. »

**Drift design `.doc` flaggé** :
- AC2 (l. 540) : « Pas de `.doc` ni `.docx` dans `accept` (le PRD backend ne les accepte pas). »
- Out-of-scope (l. 608) : « Correction du drift design `.doc` → design-system / designs/s11-frontend-upload-chat.md suggère « PDF, DOC, image » mais le backend n'accepte que `.pdf, .png, .jpg, .jpeg, .txt`. À corriger dans une future itération du design. »

## Findings

### minor — s11b — Wording « axios » dans AC3 contredit les agentic notes (carry-over)

`docs/stories.md` ligne 473. L'AC dit : « le client appelle `POST {NEXT_PUBLIC_API_URL}/api/chat/stream` (axios, `Accept: text/event-stream`, `Content-Type: application/json`) ». Les agentic notes (ligne 498) disent explicitement : « Axios ne gère PAS le streaming nativement : ne PAS utiliser `apiClient.post(...)` pour le stream (axios bufferise par défaut). Faire un `fetch` direct dans `chatStore.send` ». Le mot « axios » dans l'AC donne la direction opposée à la directive d'implémentation. **Recommandation** : remplacer « axios » par « HTTP » (ou « `fetch` direct ») dans l'AC, en déplaçant la justification dans la rationale. (Carry-over de la review précédente — toujours pending.)

### minor — s08 — Synthèse omet `partial_attempt_2` (carry-over)

`docs/stories.md` ligne 311. Les 4 ACs individuelles (l. 307-310) définissent : `partial` (échec tentative 1), `partial_attempt_2` (échec tentative 2), `full_after_attempts` (échec tentative 3), `full` (succès). Mais l'AC de synthèse « The state machine is deterministic » (l. 311) dit « failure on attempt 1 or 2 → `partial` » — ce qui omet `partial_attempt_2` et contredit l'AC précédente. **Recommandation** : réécrire la ligne de synthèse pour refléter les 4 niveaux (« success → `full`; échec t1 → `partial`; échec t2 → `partial_attempt_2`; échec t3 → `full_after_attempts` »). (Carry-over de la review précédente — toujours pending.)

### minor — s21, s22, s26 — Dépendance « s11 » obsolète (carry-over)

`docs/stories.md` lignes 1015, 1049, 1181 (zones s21 / s22 / s26). La dépendance est écrite « s11 (frontend chat page exists) » ou similaire. L'id « s11 » est obsolète : il a été splitté en s11a (shipped `c3f1829`) + s11b (fleshed out) + s11c (fleshed out). **Recommandation** : remplacer « s11 » par les sous-ids explicites dans chaque ligne de dépendance (s21 → s11b, s22 → s11b + s11c, s26 → s11b + s11c + s19). (Carry-over de la review précédente — toujours pending.)

### minor — s11c — Trap #6 redondant avec AC4 (nouveau, finding de cette review)

`docs/stories.md` ligne 584. Le trap `Intl.NumberFormat` maximumFractionDigits est déjà enforced par AC4 (« taille formatée en MB via `Intl.NumberFormat(locale, {maximumFractionDigits: 1})` »). Le trap est un rappel utile mais duplique l'AC. C'est une redondance de documentation, pas un défaut de breakdown. (Non-bloquant, signalement pour l'implémenteur : ne pas s'étonner du doublon.)

### minor — s11c — AC2 mélange 3 comportements de sélection (nouveau, finding de cette review)

`docs/stories.md` ligne 540. AC2 bunddle 3 comportements indépendants (click picker via `<label htmlFor>`, drag & drop via `onDragOver`+`onDrop`, mobile camera via `capture="environment"`) dans une seule AC. Chaque comportement est testable séparément mais le wording « supports » rend ambigu lequel échoue en cas d'échec. **Recommandation** : splitter en AC2a (click picker), AC2b (drag & drop), AC2c (mobile camera capture). (Préférence de granularité, pas un défaut — peut être laissé tel quel en planification, où chaque sous-comportement deviendra une sous-tâche.)

## Statut des 4 findings de la review précédente

| # | Finding (review `fd6cc41`) | Statut |
|---|---|---|
| 1 | s11c stub (3 ACs non testables) | **FIXED** dans `82850cb` (16 ACs fleshed out) |
| 2 | s11b wording « axios » vs « fetch » | **STILL PENDING** (re-flaggé dans cette review) |
| 3 | s08 synthèse omet `partial_attempt_2` | **STILL PENDING** (re-flaggé dans cette review) |
| 4 | s21 dépendance « s11 » ambiguë | **STILL PENDING** (re-flaggé dans cette review ; s22 et s26 partagent le même problème) |

## Verdict

Max severity: minor
Stories ready: yes

---

## Note finale sur la cohérence s11a / s11b / s11c

Le trio s11a (scaffold, shipped `c3f1829`) / s11b (chat, fleshed out) / s11c (upload, fleshed out `82850cb`) est **structurellement complet** : chaque story est un slice disjoint de l'ancien s11, et l'ordre d'exécution s11a → s11b / s11c est explicité dans les notes de chaque story.

s11c atteint le même niveau de détail que s11b : 16 ACs vérifiables, dépendances mergées vérifiées par hash, 12 pièges documentés, contraste axios/fetch avec s11b explicitement callé, drift `.doc` avec le design flaggé, les 8 états UI du contrat s10 mappés. Le finding #1 de la review précédente est entièrement résolu.

Les 5 findings minor de cette review (3 carry-overs de la review précédente + 2 nouveaux sur s11c) sont tous traitables dans des commits dédiés sans bloquer le pipeline en aval. Aucun n'est bloquant pour passer en `/ks-architect` (s11b et s11c peuvent être planifiés en parallèle de la correction de ces findings).

Fichiers consultés :
- `docs/prd.md`
- `docs/stories.md`
- `docs/reviews/stories.md` (reviews précédentes, pour réutilisation des conventions)
- `templates/stories-review-checklist.md`
