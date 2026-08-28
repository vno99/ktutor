# Review — Story Breakdown

> Revu par : sous-agent `stories-reviewer` (contexte frais).
> Date : 2026-08-28 (re-review après correction s12b → s13b)
> Source : `docs/stories.md` vs `docs/prd.md`

## Note méthodologique

Le PRD ne contient pas une table littérale « Replicated (core loop) » ni une section « Explicitly NOT replicated ». La skill `stories-review` mentionne ces noms exacts. Le sous-agent a utilisé `Périmètre (in)` et `Hors-scope (out)` comme équivalents, comme lors des reviews précédentes. Les « Métriques de succès » du PRD sont des cibles à mesurer, pas des features à shipper — elles ne mappent pas à des stories.

## Vérification du correctif s12b → s13b

| Check | Résultat |
|---|---|
| `s12b` toujours utilisé comme id de story ? | Non. N'apparaît qu'en texte historique (lignes 474, 533, 960) sous la forme « anciennement numérotée s12b ». |
| `s13b` correctement placée après `s13` dans le fichier ? | Oui. s13 démarre ligne 436, s13b démarre ligne 469, s14 démarre ligne 506. Ordre `s12 (404) → s13 (436) → s13b (469) → s14 (506) → s15 (537)` respecté. |
| Chaîne `s12 → s13 → s13b → s14 → s15` exécutable ? | Oui. Toutes les références vont vers l'arrière. Pas de cycle, pas de forward reference. |
| Dépendances de s14 mises à jour vers (s12, s13, s13b) ? | Oui (lignes 523-525). |
| Toutes les autres références à s12b mises à jour vers s13b ? | Oui. Recherche dans tout le fichier : aucun id `s12b` vivant restant, uniquement les trois mentions historiques. |
| « Ordre d'exécution suggéré » en fin de fichier correct ? | Oui. Ligne 973 : `Phase 3 (Sécurité) : s12 → s13 → s13b → s14 → s15` correspond à l'ordre du fichier et au graphe de dépendances. |
| Nouveaux problèmes introduits par le renommage ? | Aucun. Complexité 3 raisonnable, agentic notes documentent la décision, dépendance sur s13 (JWT) correctement requise. |

## Couverture du périmètre (Périmètre in)

| Périmètre PRD (in) | Story(s) | OK ? |
|---|---|---|
| Upload de documents (PDF, images dactylo, manuscrites OCR LLM) | s01, s10 | OK |
| Pipeline RAG par matière (collection par matière × élève) | s01, s05 | OK |
| Chat RAG (réponse sourcée de l'agent) | s02, s05, s09, s19 | OK |
| Génération d'exercices (QCM, problème, rédaction, flashcards) | s03, s06, s06b | OK |
| Correction progressive (QCM tout-ou-rien, rédaction appréciation LLM, 3 tentatives max) | s04, s07, s08, s20 | OK |
| Évaluations (upload copie corrigée → extraction score + annotations) | s18, s18b | OK |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s01, s10, s12-s15 + tests d'isolation dans toutes les stories API | OK |
| Authentification & RBAC (JWT RS256, admin/parent/élève, identifiés par pseudo) | s12, s13, s13b, s15 | OK |
| Dashboards (progression élève, vue parent lecture seule) | s16, s17 | OK |
| i18n (FR par défaut, EN, next-intl) | s11, s21 | OK |
| Accessibilité (responsive smartphone/tablette, WCAG 2.1 A) | s11, s22 | OK |
| Observabilité (logs structurés, OTel, Prometheus, alerting) | s23, s24 | OK |

- [x] **Chaque feature du périmètre est livrée par au moins une story** — périmètre complet.

## Graveyard (Hors-scope out)

- [x] RGPD / CNIL : pas de story. OK.
- [x] Déploiement cloud / production : pas de story. OK.
- [x] Paiements / abonnements : pas de story. OK.
- [x] Rôle enseignant : pas de story. OK.
- [x] Intégrations tierces (ENT, SI externes) : pas de story. OK.
- [x] App mobile native : pas de story. OK.
- [x] Notifications push / email : s25 explicitement in-app. OK.
- [x] Multi-langues au-delà FR/EN : s21 limité à FR/EN. OK.

**Aucune story ne réintroduit un item du graveyard.**

## Qualité des stories

- [x] Chaque story est une tranche end-to-end shippable. Persona + valeur utilisateur + critère de succès présents.
- [x] Chaque AC peut devenir un test (codes HTTP, schémas JSON, assertions RBAC, assertions d'isolation).
- [x] Notes agentic présentes et utiles dans toutes les stories (fichiers, contraintes, pièges, parfois test data).
- [x] Complexité scorée. Pas de 5. Les complexités 4 (s08, s11, s18) énoncent leur risque.
- [x] IDs bien formés `s<number>-<slug>`, uniques (s01-s26 + s06b/s13b/s18b), stables.
- [x] Pas d'overlap. s01/s10 partagent du code par design (réutilisation explicite). s04/s08 et s07/s08 empilent la correction progressive. s16/s17 empilent la vue parent sur la vue élève. Pas de duplication de valeur.

## Ordre des dépendances

Vérifié en parcourant chaque bloc « Dependencies ». Toutes les références pointent vers des stories placées plus haut dans le fichier. Pas de cycle, pas de forward reference. La nouvelle chaîne `s12 → s13 → s13b → s14 → s15` est valide.

## Findings

### minor — s12 — Référence textuelle forward à s13b

AC ligne 417 et notes agentic ligne 428 mentionnent `s13b` dans une référence textuelle forward (s13b apparaît plus loin dans le fichier). Ce n'est **pas** une dépendance déclarée — s12 ne déclare pas s13b dans ses dépendances. Pattern acceptable mais à noter pour la cohérence (le même pattern avait été flaggé pour s12b précédemment).

### minor — s18 — Référence textuelle forward à s18b

AC ligne 640 mentionne « the manual entry path is s18b ». Même pattern (mention textuelle d'une story plus tardive). Pas une dépendance. Acceptable.

### minor — s23 — Notation en plage

Dependencies ligne 837 : « All prior API stories (s09, s10, s12-s20) » utilise une notation en plage. Légèrement moins explicite qu'une liste complète, mais non ambigu en contexte. Acceptable.

### minor — s18b — Justification de la dépendance s14

Dépendance s14 (ligne 683) justifiée par « parent-child link — to authorize the linked parent ». Correct, mais le chemin « admin » de s18b ne dépend pas strictement de s14. s14 reste dans la liste de dépendances car l'autorisation du parent lié requiert que le lien existe. Justifié, pas un défaut.

## Verdict

Max severity: minor
Stories ready: yes

---

## Suite

Stories review passée. Next step: /ks-architect

Aucun finding bloquant. Les 4 findings minor sont des points de style (références textuelles forward, notation en plage) qui peuvent être nettoyés dans une itération ultérieure ou ignorés sans bloquer le pipeline.
