# Review — Story Breakdown

> Revu par : sous-agent `stories-reviewer` (contexte frais).
> Date : 2026-09-02 (re-review après étoffement de s11b-frontend-chat)
> Source : `docs/stories.md` vs `docs/prd.md`

## Note méthodologique

Le PRD ne contient pas une table littérale « Replicated (core loop) » ni une section « Explicitly NOT replicated ». La skill `stories-review` mentionne ces noms exacts. Le sous-agent utilise `Périmètre (in)` et `Hors-scope (out)` comme équivalents, comme lors des reviews précédentes. Les « Métriques de succès » du PRD sont des cibles à mesurer, pas des features à shipper — elles ne mappent pas à des stories.

## 1. Couverture du périmètre (Périmètre in)

| Périmètre PRD (in) | Story(s) | OK ? |
|---|---|---|
| Upload de documents (PDF, images dactylo, manuscrites OCR LLM) | s01, s10, s11c (stub) | OK (s11c stub à étoffer — voir finding minor) |
| Pipeline RAG par matière (collection par matière × élève) | s01, s05 | OK |
| Chat RAG (réponse sourcée de l'agent) | s02, s05, s09, s11b, s19 | OK |
| Génération d'exercices (QCM, problème, rédaction, flashcards) | s03, s06, s06b | OK |
| Correction progressive (QCM tout-ou-rien, rédaction appréciation LLM, 3 tentatives max) | s04, s07, s08, s20 | OK |
| Évaluations (upload copie corrigée → extraction score + annotations) | s18, s18b | OK |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s01, s10, s15 + tests d'isolation dans toutes les stories API | OK |
| Authentification & RBAC (JWT RS256, admin/parent/élève, identifiés par pseudo) | s12, s13, s13b, s15 | OK |
| Dashboards (progression élève, vue parent lecture seule) | s16, s17 | OK |
| i18n (FR par défaut, EN, next-intl) | s11a (scaffold), s11b (chat ns), s21 (consolidation) | OK |
| Accessibilité (responsive smartphone/tablette, WCAG 2.1 A) | s11a (scaffold), s11b (chat a11y), s22 (audit) | OK |
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

Toutes les stories sont des slices end-to-end avec valeur utilisateur (CLI command, page, endpoint). Aucune story « set up the database » ou « create the API layer » isolée. Les modèles SQLAlchemy sont créés *à l'intérieur* de la story qui en a besoin (s01, s03, s04, s12, etc.).

- [x] Aucune story n'est une couche technique seule.

## 4. AC testability check (focus s11b)

| s11b AC | Testable ? | Comment |
|---|---|---|
| AC1 (page rend avec tous les contrôles, htmlFor) | oui | Playwright DOM query + axe-core |
| AC2 (button désactivé, aria-disabled, tabindex) | oui | Playwright + `getByRole('button', { name: 'Envoyer' })` + attributs ARIA |
| AC3 (POST avec bons headers/body) | oui | Playwright `page.route` + assertion request |
| AC4 (parsing SSE token par token) | oui | Playwright stub SSE stream + DOM |
| AC5 (`role="log"`, `aria-live`, `aria-busy`) | oui | DOM + axe-core |
| AC6 (erreur 4xx/5xx et coupure de connexion) | oui | Playwright stub + DOM |
| AC7 (pseudo manquant/invalide) | oui | Playwright clear cookie + reload |
| AC8 (chatStore state) | oui | Test unitaire Zustand store |
| AC9 (responsive 360/768) | oui | Playwright viewports |
| AC10 (axe-core 0 critical/serious + Lighthouse ≥ 90) | oui | CI job |
| AC11 (5 tests e2e couvrant 5 cas) | oui | Playwright |
| AC12 (lint/typecheck/build/test exit 0) | oui | CI job |
| AC13 (commentaire head chatStore référence contrat) | vérification statique | grep du commentaire |

Toutes les ACs de s11b sont vérifiables. Le découpage est précis au point qu'il anticipe les pièges SSE (Piège #2 recherche + ADR 006).

s11c a 3 ACs au niveau résumé — non testables tels quels. Voir finding ci-dessous.

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
- **s11b → s11a (merged `c3f1829`), s09 (merged `c5f6163`), s10 (merged `ff21046`)** OK
- s11c → s11a OK
- s12 → s01 OK
- s13 → s12 OK
- s13b → s12, s13 OK
- s14 → s12, s13, s13b OK
- s15 → s13, all prior API endpoints OK
- s16 → s04, s07, s15 OK
- s17 → s14, s15, s16 OK
- s18 → s10, s15 OK
- s18b → s18, s14, s15 OK
- s19 → s15 OK
- s20 → s04, s07, s08, s16 OK
- s21 → s11b (et s11c si consolidation i18n touche la page upload) — voir finding minor
- s22 → s11 OK
- s23 → s09, s10, s12-s20 OK
- s24 → s23 OK
- s25 → s18, s20 OK
- s26 → s11, s16, s17, s18, s20 OK

No cycles, no forward references among declared dependencies. La correction `s12b → s13b` (résolue lors de la review précédente) reste valide.

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
- **s11b: 3** (page + SSE consumer + store + i18n + a11y + 5 e2e — voir note)
- s11c: 2 (stub — voir finding)
- s12: 2
- s13: 3
- s13b: 3
- s14: 2
- s15: 3
- s16: 3
- s17: 3 (relevée de 2 à 3, risk stated)
- s18: 4 (risk stated — LLM vision non-deterministic)
- s18b: 2
- s19: 2
- s20: 3
- s21: 3 (relevée de 2 à 3, risk stated)
- s22: 3
- s23: 3
- s24: 2
- s25: 3
- s26: 1

No 5, all 4s state their risk. La règle d'or (4 = risk stated, 5 = must split) est respectée.

Note sur s11b (complexity 3) : la story couvre page + fetch SSE + ReadableStream + chatStore Zustand + 13 ACs + 5+ tests e2e. C'est consistant avec s11a (scaffold from zero) qui est aussi à 3. Pas un finding.

## 7. ID format & uniqueness

Format `s<number>-<slug>` partout. Suffixes valides : s06b, s13b, s18b. Pas de doublon, pas de régression. L'ancien id `s12b` n'apparaît plus qu'en référence historique (l. 474, 533, 960 — toutes marquées « anciennement numérotée s12b »). Conforme à la review précédente.

## 8. s11b / s11c focus

**s11b est shippable-ready** :
- 13 ACs, chacune testable, chacune ancrée à un comportement observable (DOM, attribut ARIA, requête HTTP, message inline, test e2e).
- Dépendances vérifiées par commit hash (`c3f1829`, `c5f6163`, `ff21046`).
- Agentic notes très complètes : 5 pièges documentés (SSE buffering Next.js, EventSource vs fetch ADR 006, tokens vides en début de stream, prefers-reduced-motion, lien désactivé dans header), 3 open questions tranchées, out-of-scope explicite.
- Le commentaire de tête de `chatStore.ts` exigé par AC13 verrouille le couplage au contrat s09.

**s11c est un stub assumé** :
- 3 ACs au niveau résumé, marqués « (résumé) ».
- Le trio s11a (shipped) / s11b (fleshed out) / s11c (stub) reste cohérent (chaque story est un slice disjoint de l'ancien s11), mais s11c n'est pas prêt à être planifié tant qu'il n'a pas été étoffé.
- Le stub ne casse pas la breakdown, mais il est *insuffisant* pour la phase `/ks-research` (rien à researcher sur 3 lignes).

## Findings

### minor — s11c — Story stub, 3 ACs non testables

Fichier `docs/stories.md` lignes 527-541. La story est un placeholder de 3 ACs (« sélection de fichier, choix de matière, soumission. Succès → confirmation. Erreur → message clair. »). Ces ACs sont au niveau résumé, pas au niveau testable. Le trio s11a (shipped) / s11b (fleshed out) / s11c (stub) reste cohérent, mais s11c ne peut pas passer en `/ks-research`/`/ks-plan`/`/ks-execute` tant qu'il n'a pas été étoffé en suivant le même niveau de détail que s11b (ACs observables, dépendances, agentic notes avec pièges documentés). **Recommandation** : étoffer s11c dans un commit dédié avant de planifier, en s'inspirant du niveau de détail de s11b (drag & drop + caméra mobile, axios vs fetch, multi-tenant, e2e).

### minor — s11b — Incohérence interne « axios » vs « fetch »

AC3 (l. 473) : « le client appelle `POST {NEXT_PUBLIC_API_URL}/api/chat/stream` (axios, `Accept: text/event-stream`, `Content-Type: application/json`) ». Mais l'Agentic notes « Constraints » (l. 498) dit explicitement : « Axios ne gère PAS le streaming nativement : ne PAS utiliser `apiClient.post(...)` pour le stream (axios bufferise par défaut). Faire un `fetch` direct dans `chatStore.send` ». Le mot « axios » dans l'AC contredit la directive d'implémentation. **Recommandation** : remplacer « axios » par « HTTP » (ou « `fetch` direct ») dans l'AC, et déplacer la justification dans la rationale.

### minor — s08 — Incohérence interne des niveaux de correction

ACs (l. 307-310) introduisent 4 niveaux : `partial` (tentative 1 échouée), `partial_attempt_2` (tentative 2 échouée), `full_after_attempts` (tentative 3 échouée), `full` (succès). Mais l'AC de synthèse « The state machine is deterministic » (l. 311) dit « failure on attempt 1 or 2 → `partial` » — ce qui omet `partial_attempt_2` et contredit l'AC précédente. **Recommandation** : mettre à jour la phrase de synthèse pour refléter les 4 niveaux (partial → partial_attempt_2 → full_after_attempts, et success → full).

### minor — s21 — Dépendance « s11 » ambiguë

Dépendance déclarée (l. 753) : « s11 (frontend chat page exists) ». Le « s11 » est aujourd'hui splitté en s11a/s11b/s11c. Le sens pratique est « s11b shippé » (la page `/chat` est le sujet de la dépendance), mais l'ID utilisé est l'ancien. **Recommandation** : clarifier en « s11b-frontend-chat » (et possiblement ajouter s11c si la consolidation i18n doit aussi toucher la page upload).

## Verdict

Max severity: minor
Stories ready: yes

---

## Note finale sur la cohérence s11a/s11b/s11c

Le trio s11a (scaffold, shipped) / s11b (chat, fleshed out) / s11c (upload, stub) est **structurellement cohérent** : chaque story est un slice disjoint de l'ancien s11, et l'ordre d'exécution s11a → s11b / s11c est explicité dans les notes de chaque story. Le stub s11c n'introduit pas de gap silencieux dans la breakdown — il est reconnu comme tel et attend son étoffement.

s11b est shippable-ready au sens « la prochaine étape est `/ks-research` puis `/ks-plan` » : ses ACs sont vérifiables, ses dépendances sont mergées et vérifiées par hash, ses pièges sont documentés, et ses out-of-scope sont explicites (persistance historique → s19, bouton Stop → s22, streaming JWT → trivial refacto en s15).

s11c n'est *pas* shippable-ready et ne doit pas être planifié tant qu'il n'est pas étoffé. C'est un point de vigilance à noter pour la suite, pas un blocage de la breakdown actuelle.

Les 4 findings minor identifiés (s11c stub, s11b axios/fetch, s08 partial/partial_attempt_2, s21 dépendance ambiguë) sont traitables dans des commits dédiés sans bloquer le pipeline en aval. Aucun n'est bloquant pour passer en `/ks-architect` (s11b peut être planifié en parallèle de l'étoffement de s11c).

Fichiers consultés :
- `docs/prd.md`
- `docs/stories.md`
- `docs/reviews/stories.md` (review précédente, pour réutilisation des conventions)
- `templates/stories-review-checklist.md`
