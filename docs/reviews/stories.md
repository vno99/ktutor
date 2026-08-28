# Review — Story Breakdown

> Revu par : sous-agent `stories-reviewer` (contexte frais).
> Date : 2026-08-28 (re-review après commit correctif)
> Source : `docs/stories.md` vs `docs/prd.md`

## Note méthodologique

Le PRD ne contient pas une table littérale « Replicated (core loop) » ni une section « Explicitly NOT replicated ». La skill `stories-review` mentionne ces noms exacts. Le sous-agent a utilisé `Périmètre (in)` et `Hors-scope (out)` comme équivalents, comme lors de la review précédente.

## Vérification des correctifs annoncés par l'auteur

| Correctif annoncé (issue de la review précédente) | État | Note |
|---|---|---|
| **critical** — s06b-generer-flashcards ajoutée | OK | Story shippable, AC testables, complexité 3, dépendances s01/s02/s03 saines. Couvre le type d'exercice « flashcards » du périmètre. |
| **major** — s12b-creer-compte-admin-parent ajoutée | PARTIEL | Story livrée, AC testables, scope correct (POST /users + PUT /users/{pseudo}/role + garde « last admin »). **Mais** voir finding major §5 — chaîne de dépendances cassée. |
| **major** — s18b-evaluation-actions-admin ajoutée | OK | Story shippable, AC testables, scope correct (score-manual + reprocess), dépendances s18/s14/s15 saines. |
| **minor** — wording s22 nettoyé | OK | Plus de caractère chinois parasite. |
| **minor** — wording s20 clarifié (3 tentatives max + 4e = 409) | OK | Cohérent avec s08. |
| **minor** — s08 ajout AC 409 sur 4e tentative | OK | « A test verifies that an attempt_number > 3 on the same exercise returns 409 ». |
| **minor** — s17 complexité 2 → 3 + risque explicité | OK | Complexité 3, risque documenté (réutilisation du composant eleve). |
| **minor** — s21 complexité 2 → 3 + risque explicité | OK | Complexité 3, risque documenté (frontend next-intl + backend Accept-Language). |
| **minor** — s06 référence stale STORY-016 | OK | Pointe désormais sur la question ouverte n°2 du PRD, dans la phase Research de s06. |

Aucun finding de la review précédente n'a été affaibli ou abandonné — tous sont traités ou améliorés.

## Couverture du périmètre (Périmètre in)

| Périmètre PRD (in) | Story(s) | OK ? |
|---|---|---|
| Upload de documents (PDF, images dactylo, manuscrites OCR LLM) | s01 (CLI), s10 (API) | OK |
| Pipeline RAG par matière (collection par matière × élève) | s01, s05 | OK |
| Chat RAG (agent spécialisé par matière) | s02, s05 | OK |
| Génération d'exercices — QCM | s03 | OK |
| Génération d'exercices — problème | s06 | OK |
| Génération d'exercices — rédaction | s06 | OK |
| Génération d'exercices — flashcards | s06b | OK (réparé) |
| Correction progressive (3 tentatives max) | s04, s07, s08 | OK |
| Évaluations (upload + extraction score + annotations) | s18, s18b | OK (réparé) |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s15 + tests cross-tenant dans s10/s16/s17/s18/s20 | OK |
| Authentification & RBAC (JWT RS256, admin/parent/élève, pseudo) | s12, s12b, s13, s14, s15 | OK (réparé) |
| Dashboards (élève + parent lecture seule) | s16, s17 | OK |
| i18n (FR/EN, next-intl) | s21 | OK |
| Accessibilité (responsive, WCAG 2.1 A) | s11, s22 | OK |
| Observabilité (logs, OTel, Prometheus, alerting) | s23, s24 | OK |

- [x] **Chaque feature du périmètre est livrée par au moins une story** — périmètre complet.

## Graveyard (Hors-scope out)

| Item hors-scope | Fuite ? | OK ? |
|---|---|---|
| RGPD / CNIL / données personnelles | non | OK |
| Déploiement cloud / production | non | OK |
| Paiements / abonnements | non | OK |
| Rôle enseignant | non | OK |
| Intégrations tierces (ENT, Pronote…) | non | OK |
| App mobile native | non (web responsive uniquement) | OK |
| Notifications push / email | non (s25 explicitement in-app) | OK |
| Multi-langues au-delà FR/EN | non (s21 limité à FR/EN) | OK |

- [x] **Aucune story ne réintroduit un item du graveyard.**

## Qualité des stories

- [x] Chaque story est une tranche end-to-end shippable. Les trois nouvelles stories (s06b, s12b, s18b) passent chacune le test : persona + valeur utilisateur + critère de succès.
- [x] Chaque AC peut devenir un test. Les AC des trois nouvelles stories spécifient des codes HTTP, des schémas JSON, des assertions de RBAC, des assertions d'isolation.
- [x] Notes agentic présentes et utiles dans toutes les stories (fichiers, contraintes, pièges, parfois test data). s12b et s18b ont des traps ciblées (« last admin race condition », « parent-child link lookup dans le path d'autorisation »).
- [x] Complexité scorée. Pas de 5. Les complexités 4 (s08, s11, s18) énoncent leur risque. s12b à 3, s18b à 2 — cohérent avec le scope.
- [x] IDs bien formés `s<number>-<slug>`, uniques (s01-s26 + s06b/s12b/s18b), stables.
- [x] Pas d'overlap. s06 / s06b sont deux types d'exercice distincts (probleme|redaction vs flashcards). s12 / s12b sont deux paths de création (élève public vs admin/parent). s18 / s18b sont deux actions (upload vs remédiation post-extraction).

## Ordre des dépendances

L'ordre s01 → … → s26 est globalement exécutable, à l'**exception d'un forward reference** dans s12b :

**s12b déclare comme dépendances :**
- s12 (User model exists) — OK, position précédente.
- s13 (JWT middleware exists — to verify the `admin` role).

**Or :**
- s12b est placée en position 2 dans la Phase 3 (entre s12 et s13).
- L'« Ordre d'exécution suggéré » en fin de fichier confirme : `s12 → s12b → s13 → s14 → s15`.
- L'AC de s14 dit textuellement : « The dependency chain is now: s12 → s12b → s13 → s14 ».

**Le problème :** les AC de s12b exigent un test « A non-admin caller gets 403 » et « an admin can create a `parent` user ». Ces tests requièrent :
1. Un mécanisme d'authentification pour distinguer admin / non-admin (JWT, donc s13).
2. Une stratégie de test où « the test client logs in as that admin » (notes agentic de s12b) — login = s13.

Suivre l'ordre déclaré `s12 → s12b → s13` rend s12b impossible à exécuter : aucun mécanisme d'auth n'existe pour valider le rôle.

**Deux fixes possibles (à choisir par l'auteur) :**
- (a) Réordonner : `s12 → s13 → s12b → s14 → s15`. Le forward reference disparaît, s14 garde toutes ses dépendances (s12, s12b, s13).
- (b) Laisser s12b avant s13, mais lui faire utiliser un stub d'auth en `pseudo+role` dans le body (analogue à s09, s10), et l'ajouter à la liste de migration JWT de s15. Dans ce cas, s12b ne devrait pas déclarer s13 en dépendance et la note de s14 serait corrigée.

L'auteur doit choisir l'une des deux options. Le défaut actuel (forward reference) viole la règle « no forward reference ».

Aucun autre cycle ni forward reference détecté. s15 dépend bien de s13 et de l'ensemble des endpoints antérieurs. s17 dépend de s14/s15/s16 dans le bon ordre. s20 dépend de s04/s07/s08/s16.

## Findings

### major — s12b — Forward reference sur s13 (chaîne de dépendances cassée)

s12b déclare « s13 (JWT middleware exists — to verify the `admin` role) » comme dépendance mais est placée avant s13 dans le fichier. L'« Ordre d'exécution suggéré » et la note de s14 entérinent l'ordre cassé `s12 → s12b → s13 → s14`. Conséquence : s12b ne peut pas être exécutée en l'état — ses tests « 403 pour non-admin » et « admin crée parent » présupposent un middleware JWT qui n'existe pas encore. Fix : réordonner en `s12 → s13 → s12b → s14 → s15`, OU faire de s12b une story à stub d'auth migrée par s15 (auquel cas la dépendance s13 disparaît et s15 doit ajouter s12b à sa liste de migration à côté de s09, s10).

## Verdict

Max severity: major
Stories ready: no

---

## Suite

Stories review bloquée (major). Corriger `docs/stories.md` — choisir l'une des deux options ci-dessus pour s12b, puis relancer `/ks-stories-review`.

Actions prioritaires :
1. **Réordonner s12b** après s13 (chemin recommandé), ou la passer en stub d'auth avec migration dans s15. Une seule des deux — l'état actuel mélange les deux et casse la chaîne.
2. Aucun autre finding à corriger.
