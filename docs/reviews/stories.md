# Review — Story Breakdown

> Revu par : sous-agent `stories-reviewer` (contexte frais).
> Date : 2026-08-28
> Source : `docs/stories.md` vs `docs/prd.md`

## Note méthodologique

Le PRD ne contient pas une table littérale « Replicated (core loop) » ni une section « Explicitly NOT replicated ». La skill `stories-review` mentionne ces noms exacts. Le sous-agent a utilisé `Périmètre (in)` et `Hors-scope (out)` comme équivalents. Si la convention du projet exige l'une de ces deux tables, il faudrait soit les ajouter au PRD, soit renommer les sections existantes — sans cela, la prochaine review risque de tourner en rond sur le même malentendu.

## Couverture du périmètre (Périmètre in)

| Périmètre PRD (in) | Story(s) candidate(s) | OK ? |
|---|---|---|
| Upload de documents (PDF, images dactylo, manuscrites via OCR LLM) | s01 (CLI), s10 (API) | OK |
| Pipeline RAG par matière (ingestion → chunking → embeddings → ChromaDB, une collection par matière × élève) | s01, s05 | OK |
| Chat RAG (questions en langage naturel, agent spécialisé par matière) | s02, s05 | OK |
| Génération d'exercices — QCM | s03 | OK |
| Génération d'exercices — problème | s06 | OK |
| Génération d'exercices — rédaction | s06 | OK |
| Génération d'exercices — **flashcards** | **aucune** (s06 ne couvre que `probleme|redaction` ; les notes de fin admettent le drop) | **FAIL** |
| Correction progressive (QCM tout-ou-rien, rédaction appréciation LLM, 3 tentatives max) | s08 | OK |
| Évaluations (upload copie corrigée → extraction score + annotations) | s18 (upload + extraction). Mais `POST /evaluations/{id}/score-manual` et `POST /evaluations/{id}/reprocess` (CLAUDE.md) ne sont pas dans une story. | PARTIEL |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s01, s15 + tests d'isolation dans s10, s16, s17, s18, s20 | OK |
| Authentification & RBAC (JWT RS256, admin/parent/élève, pseudo) | s12 (élève), s13 (JWT), s14 (parent↔enfant), s15 (RBAC transverse). Mais aucune story ne crée de compte `parent` ou `admin` ni n'assigne un rôle non-élève. | PARTIEL |
| Dashboards (progression élève, vue parent lecture seule) | s16, s17 | OK |
| i18n (FR par défaut, EN, next-intl) | s21 (s11 amorce) | OK |
| Accessibilité (responsive smartphone/tablette, WCAG 2.1 A) | s11 (responsive de base), s22 (audit + a11y complet) | OK |
| Observabilité (logs structurés, OpenTelemetry, Prometheus, alerting) | s23, s24 | OK |

- [ ] **Chaque feature du périmètre est livrée par au moins une story — FAIL** (flashcards droppées ; création de comptes non-élève absente)

## Graveyard (Hors-scope out)

| Item hors-scope (out) | Fuite dans une story ? | OK ? |
|---|---|---|
| RGPD / CNIL / données personnelles | non | OK |
| Déploiement cloud / production, Kubernetes, CI/CD prod | non | OK |
| Paiements / abonnements / Stripe | non | OK |
| Rôle enseignant | non | OK |
| Intégrations tierces (ENT, Pronote, ÉcoleDirecte, Google Classroom) | non | OK |
| App mobile native | non | OK |
| Notifications push / email | non (s25 explicitement in-app) | OK |
| Multi-langues UI au-delà de FR/EN | non (s21 limité à FR/EN) | OK |

- [x] **Aucune story ne réintroduit un item du graveyard**

## Qualité des stories

- [x] Chaque story est une tranche end-to-end shippable, pas une couche technique. Aucune story n'est purement « set up the database » ou « create the API layer ». s05 introduit le superviseur en même temps que l'agent français — borderline, mais shippable car l'agent répond à un utilisateur.
- [x] Chaque critère d'acceptation peut devenir un test (critères concrets, données de test évoquées, codes retour HTTP, regex, seuils).
- [x] Notes agentic présentes et utiles (fichiers impliqués, contraintes, pièges dans toutes les stories).
- [x] Complexité scorée. Pas de 5. Chaque 4 (s08, s11, s18) énonce son risque dans les notes agentic.

## L'ensemble

- [x] Pas de cycle, pas de référence forward. L'ordre s01 → … → s26 est exécutable.
- [x] Ids bien formés (`s<number>-<slug>`), uniques, stables (s01 à s26, pas de doublon).
- [x] Pas de vrai overlap. s03 et s06 partagent le modèle `Exercise` mais s06 en est une extension downstream (dépendances respectées). s04 et s07 écrivent dans le même modèle `Attempt` mais pour des flux distincts (QCM vs texte libre) — pas une duplication de valeur.

## Findings

### critical — coverage — Les flashcards sont dans le périmètre mais absentes des stories

Le PRD liste « QCM, problème, rédaction, flashcards » comme types d'exercices à générer. s06 ne couvre que `probleme|redaction` ; les notes de fin du document admettent « Les flashcards peuvent être une story ultérieure si besoin ». Une feature du périmètre est silencieusement droppée et n'apparaît qu'en fin de document.

### major — coverage — Aucune story ne crée de compte `parent` ou `admin` ni ne change un rôle

s12 fixe `role='eleve'` par défaut et aucune autre story ne s'en écarte. Pourtant s14 (lier parent ↔ enfant), s15 (admin bypass) et s17 (dashboard parent) en dépendent. Pour qu'un parent puisse se lier, il faut un compte `parent` existant ; pour que l'admin puisse bypass, il faut un compte `admin` — sans story, l'arbre de dépendances casse en pratique.

### major — coverage — Les endpoints `POST /evaluations/{id}/score-manual` et `POST /evaluations/{id}/reprocess` ne sont livrés par aucune story

Définis dans CLAUDE.md, et la storyline de s18 y fait référence (« prompts the user (or an admin) to enter the score manually »). s18 couvre `POST /api/evaluations/upload` mais pas les deux autres. Le fallback `manual_review_needed` de s18 n'a pas de chemin de remédiation.

### minor — s22 — Caractère chinois dans le wording utilisateur

L'énoncé utilisateur contient « 障碍 » au milieu d'une phrase française (« … que je puisse utiliser l'app sans障碍 »). Probablement un artefact d'encodage / typo. À corriger dans le wording.

### minor — s21 — Scope mixte frontend / backend sous-évalué

Le scope mélange i18n frontend (next-intl, message catalogs) et i18n backend (Accept-Language) dans une seule story de complexité 2. Shippable, mais le rating sous-estime deux surfaces techniques très différentes.

### minor — s17 — Complexité annoncée 2 sous-évaluée

La story cumule endpoint parent, page liste, page child-detail, vérification que la `child-detail` est en lecture seule et tests d'isolation. Le « re-use » de s16 n'est pas aussi simple qu'annoncé. Pas un blocker, mais le risque mérite d'être explicité comme pour les autres 4.

### minor — s14 — AC fragilisée par l'absence de création d'admin

AC « Only an admin (or the parent themselves, in a follow-up) can create the link » ne précise pas qui authentifie l'admin puisque aucune story ne crée d'admin. Lié au gap critique sur la création de rôles non-élève, mais localement ça fragilise la testabilité de l'AC.

### minor — s20 — Incohérence wording 3 vs 4 tentatives

L'AC « After 3 failed attempts, the full correction is shown but no points are awarded » et la trap « the student can submit the same exercise 4 times (3 fails + 1 final with full solution shown) » sont incohérentes : la 3e tentative est celle qui déclenche `full_after_attempts`, donc la 3e soumission est aussi la dernière utile, pas une 4e. Wording à clarifier.

### minor — s06 — Référence stale vers une question ouverte du PRD

« Open question (PRD § Questions ouvertes) : le PRD pointe ce sujet sur STORY-016, pas sur cette story. » Référence stale.

## Verdict

Max severity: critical
Stories ready: no

---

## Suite

Stories review bloquée (critical). Corriger `docs/stories.md` — relancer `/ks-stories` ou l'éditer directement — puis relancer `/ks-stories-review`.

Actions prioritaires :
1. **Restaurer les flashcards dans le périmètre** (story dédiée ou intégration à s06).
2. **Ajouter une story de gestion des comptes non-élève** : création de compte `parent` et `admin` + endpoint de mise à jour de rôle. Sans cela, s14, s15, s17 ne sont pas testables.
3. **Compléter s18** (ou ajouter une story) pour livrer `POST /evaluations/{id}/score-manual` et `POST /evaluations/{id}/reprocess`.
4. Corriger les findings minor (wording s22, s20 ; clarifier la complexité s17, s21 ; fixer la référence stale s06).
