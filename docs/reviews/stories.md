# Review — Story Breakdown

> Revu par : **non exécuté** (échec infrastructurel, voir ci-dessous).
> Date : 2026-08-27
> Source : `docs/stories.md` vs `docs/prd.md`

## Statut

**La review n'a pas pu être exécutée.** Le sous-agent `stories-reviewer` a échoué deux fois de suite avec l'erreur suivante (provider sous-traitant) :

```
API Error: 402 Insufficient credits.
This account never purchased credits.
Make sure your key is on the correct account or org,
and if so, purchase more at https://openrouter.ai/settings/credits
```

Le contrat de `/ks-stories-review` interdit explicitement au parent agent de juger lui-même les stories (risque de biais de confirmation, c'est le contexte qui les a écrites). Aucune review n'est donc publiée.

## Couverture PRD (audit partiel fait par le parent — non substituable à la review)

> ⚠️ L'audit ci-dessous est informatif et ne constitue PAS la review officielle. Il est fourni pour aider l'humain à décider de la suite.

Le parent agent a vérifié manuellement que les grandes lignes du périmètre du PRD (`docs/prd.md` § Périmètre in) semblent couvertes par les stories shippées. Ce mapping est à valider par un agent frais ou par un humain.

| Périmètre PRD (in) | Story(s) candidate(s) | Couverture |
|---|---|---|
| Upload PDF/image dactylo/image manuscrite | s01 | ✅ |
| Pipeline RAG par matière (ChromaDB) | s01 | ✅ |
| Chat RAG | s02, s05 | ✅ |
| Génération QCM | s03 | ✅ |
| Génération problème / rédaction | s06 | ✅ |
| Génération flashcards | s06 (fusionné) | ⚠️ fusionnée — à valider |
| Correction progressive (QCM tout-ou-rien, rédaction appréciation) | s04, s07, s08 | ✅ |
| Évaluations (upload copie + extraction score) | s18 | ✅ |
| Multi-tenancy (PostgreSQL, ChromaDB, MinIO, JWT) | s15 + tests d'isolation dans chaque story API | ✅ (transverse) |
| Authentification JWT RS256 | s12, s13 | ✅ |
| RBAC admin/parent/élève | s13, s14, s15 | ✅ |
| Dashboards élève | s16 | ✅ |
| Dashboard parent (lecture seule) | s17 | ✅ |
| i18n FR/EN | s21 | ✅ |
| Accessibilité responsive WCAG 2.1 A | s22 | ✅ |
| Observabilité (logs, traces, métriques, alerting) | s23, s24 | ✅ |

| Périmètre PRD (out) — risque de fuite | Présent dans les stories ? |
|---|---|
| RGPD / CNIL | ❌ (correct, hors-scope) |
| Paiements | ❌ (correct) |
| Rôle enseignant | ❌ (correct) |
| Intégrations tierces (ENT) | ❌ (correct) |
| App mobile native | ❌ (correct) |
| Notifications push / email | ❌ (correct — s25 = in-app uniquement) |
| Multi-langues > FR/EN | ❌ (correct) |
| Déploiement cloud / production | ❌ (correct) |

## Suite

### Pour débloquer la review

L'utilisateur doit soit :
1. **Recharger des crédits** sur le provider (https://openrouter.ai/settings/credits), puis relancer `/ks-stories-review` (l'agent sous-traitant fonctionnera à nouveau).
2. **Faire la review manuellement** en suivant la checklist `templates/stories-review-checklist.md`, puis écrire le verdict dans ce fichier (`docs/reviews/stories.md`) avec les lignes exactes `Max severity: ...` et `Stories ready: yes|no`, et committer.

### Conséquence sur le pipeline

`/ks-architect` peut être lancé **en connaissance de cause** (le gate est *soft* par construction, il ne bloque pas mécaniquement). Mais la review officielle reste à faire pour ne pas naviguer à l'aveugle sur les phases suivantes.

---

Max severity: major
Stories ready: no
