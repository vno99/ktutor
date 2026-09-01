---
name: design-s07-repondre-texte-libre
description: s07-repondre-texte-libre — la story est purement backend, aucun écran à concevoir. Le LLM-as-judge est non-déterministique : le contrat de sortie doit être absorbé par l'UI sans halluciner la confiance dans le verdict.
metadata:
  type: project
  story: s07-repondre-texte-libre
---

# Design — Story s07-repondre-texte-libre

> **Aucun écran à produire.** Cette story est purement backend (grader LLM-as-judge pour les exercices libres, persistance Attempt). Tous les acceptance criteria portent sur la CLI, la couche de service, ou les tests. Aucun composant du design system n'est consommé.

## Rappel de la story

**As an** élève **I want** soumettre ma réponse (texte) à un exercice de type problème ou rédaction **so that** je reçoive une appréciation qualitative (positive ou échec) du LLM.

**Complexity** : 3 — LLM-as-judge + prompt engineering + parsing + persistence.

**Dépendance amont** : s06 (génération d'exercices `probleme` / `redaction`). La `expected_answer` et les `grading_criteria` sont lues depuis l'`Exercise` créé par s06.

### Acceptance criteria (résumé)

| AC | Surface | Type |
| --- | --- | --- |
| AC1 | CLI : `submit-text --exercise-id <id> --answer "..."` | **CLI flag** (typer) |
| AC2 | Prompt LLM compare à `expected_answer`, retourne verdict + feedback | **Logique LLM** |
| AC3 | Parsing strict regex `/VERDICT:\s*(REUSSITE|ECHEC)/i`, retry une fois | **Logique parsing** |
| AC4 | Persistance `Attempt` (réutilise s04, champ `answer_text` au lieu de `answers`) | **Backend service** |
| AC5 | Test stub LLM `VERDICT: REUSSITE` → `is_success=true` | **Test** |
| AC6 | Test stub LLM sans `VERDICT:` → retry puis échec | **Test** |
| AC7 | Test cross-tenant `pseudo_a`/`pseudo_b` | **Test** |

**Aucune surface UI/Web.** Le grader sera déclenché par la CLI (`backend/app/cli.py`) ou par une future API REST (s09-s11).

## Pourquoi pas de design

Règle du contrat ks-design (lignes du skill) :

> **Vous êtes INTERDIT de** :
> - Produire un design sans design system existant.
> - Inventer un composant, token, couleur ou espacement en dehors du design system.
> - Concevoir un écran que la story ne demande pas.

Cette story ne demande aucun écran. Produire un mockup HTML ici violerait la troisième interdiction.

## Écrans futurs qui consommeront l'API s07

Le grader de s07 sera consommé visuellement par les stories UI suivantes, **pas avant** :

| Écran | Story | Composants DS consommés | Notes |
| --- | --- | --- | --- |
| `/exercises/{id}` (page de réponse à un exercice) | **s11-frontend-upload-chat** (extension) ou **story dédiée après s11** | `<Card>` (énoncé), `<Textarea>` (réponse), `<Button>` (soumettre), `<Toast>` (verdict) | Écran principal de consommation |
| Historique des tentatives | **s19-historique-conversations** (extension) | `<Table>`, `<Card>` (verdict + feedback) | « Mes 5 dernières tentatives sur cet exercice » |
| Dashboard parent (vue enfant) | **s17-dashboard-parent** | `<Tabs>`, `<Card>`, `<Chart>` | Statistiques de réussite par exercice |

**Aucun de ces écrans n'est dans le périmètre de s07.** Ils seront conçus au moment de leur story respective via `/ks-design <story>`, qui lira **ce document** pour comprendre le contrat de sortie du grader.

## Particularité « LLM-as-judge est non-déterministique »

**Contrainte critique** documentée dans `docs/stories.md:288` et dans CLAUDE.md § Workflows Clés § 2.b (« Rédaction / Problème : appréciation qualitative du LLM (positive ou échec) »).

Implications pour les futures stories UI :

1. **Le verdict n'est PAS une vérité absolue.** Une même réponse peut recevoir `REUSSITE` une fois et `ECHEC` une autre fois (temperature > 0, stochasticité du LLM). L'UI doit **communiquer cette incertitude** à l'élève sans le décourager.

2. **Le feedback est une phrase, pas un diagnostic.** Le LLM produit une appréciation qualitative courte (« La démarche est correcte, mais le calcul final est erroné »). L'UI doit l'afficher tel quel, sans le tronquer ni l'embellir.

3. **Le `is_success` binaire est une simplification.** Le PRD impose « tout ou rien » pour s07 (s08 introduira la nuance plus tard). L'UI doit traiter `is_success=true` comme « la réponse est jugée satisfaisante » et `is_success=false` comme « la réponse est jugée insuffisante » — pas comme « bonne/mauvaise ».

4. **Le retry côté backend** (AC3) signifie que l'élève peut attendre jusqu'à **2× la latence LLM** en cas de verdict mal parsé. L'UI doit montrer un état de chargement prolongé (15-30s possibles).

## Contrat de sortie à fixer pour les stories en aval

Bien que s07 ne produise pas d'écran, le contrat de sortie du `TextGrader` est **imposé** aux futures stories UI. Documenter ici pour qu'elles le respectent sans réinventer.

### Format JSON (CLI → future UI)

```typescript
type TextGradingResult = {
  is_success: boolean;            // true = REUSSITE, false = ECHEC
  feedback: string;               // 1 phrase qualitative du LLM (max ~500 chars recommandé)
  attempt_number: int;            // 1, 2, 3, ... (s08 ferme après 3)
  attempt_id: string;             // UUID v4
};
```

### Erreurs typées (mapper à des exit codes HTTP / CLI)

| `kind` | Exit code | Sens UI |
| --- | --- | --- |
| `exercise_not_found` | 5 | « Cet exercice n'existe pas » — vérifier l'ID |
| `cross_tenant` | 5 | (même message que not_found — pas de leak) |
| `verdict_missing` | 4 | « Le service n'a pas pu analyser ta réponse. Réessaye. » |
| `llm_failure` | 4 | « Le service d'analyse est indisponible. Réessaye dans quelques minutes. » |
| `answer_too_long` | 2 | « Ta réponse dépasse la limite (N caractères). Raccourcis-la. » |
| `invalid_exercise_type` | 4 | « Cet exercice n'accepte pas les réponses texte. » (soumis à un QCM par erreur) |

### Comportement UI attendu (à implémenter dans les stories futures)

#### Écran de réponse à un exercice (`/exercises/{id}`)

- **Enoncé** : `<Card>` en haut, contenant `statement` (l'`Exercise.statement` créé par s06). `text-base`, padding 16-20px. Pas de bouton de retour — l'élève est en focus.
- **Critères d'évaluation** : section repliable `<details>` sous l'énoncé, label « Critères d'évaluation » (i18n via `next-intl`). Contenu en `text-text-secondary`, `text-sm`. Permet à l'élève de structurer sa réponse.
- **Zone de réponse** : `<Textarea>` plein largeur, `min-height: 200px`, `placeholder` « Écris ta réponse ici ». Compteur de caractères en bas à droite (« 245 / 8000 »), `text-text-tertiary`. Limite soft : 8000 chars (configurable côté backend, `text_grader_max_answer_chars`).
- **Bouton** : `<Button variant="primary">` « Soumettre ma réponse ». `disabled` tant que la réponse est vide OU > 8000 chars.
- **État de chargement** : 3 points animés (cf. design system ligne 221) sur le bouton, `aria-busy="true"`, latence typique **10-30s** (2 appels LLM possibles si retry).
- **Verdict succès** (`is_success=true`) :
  - `<Toast>` vert (4s, `role="status"`) « Bonne réponse ! » en haut
  - `<Card>` dédiée sous la zone de réponse, fond `bg-success/10` (vert léger), bordure gauche 4px `--color-success`. Contenu : le `feedback` du LLM en `text-base`. Bouton « Voir la correction complète » (s08) si dispo.
- **Verdict échec** (`is_success=false`) :
  - **PAS de Toast rouge** (trop dur après un effort). `<Card>` dédiée, fond `bg-warning/10` (orange léger), bordure gauche 4px `--color-warning`. Contenu : le `feedback` du LLM en `text-base`. Bouton « Réessayer » (l'élève peut re-tenter, sauf si `attempt_number >= 3` → voir s08).
  - **Disclaimer discret** : petit texte en `text-text-tertiary`, `text-xs` : « L'appréciation est fournie par l'IA. Demande à ton enseignant si tu as un doute. »
- **État d'erreur** (verdict_missing, llm_failure) : `<Toast>` rouge 4s (`role="status"`) « Le service n'a pas pu analyser ta réponse. Réessaye. » + bouton « Réessayer » dans la `<Card>` de feedback (si pas de réponse affichée).
- **Multi-tenant** : côté UI, le `pseudo` vient du JWT (s12). La UI ne le demande jamais.

#### Écran d'historique des tentatives (s19 extension)

- **Liste** : `<Table>` avec colonnes : `#`, `Date`, `Verdict` (badge vert/rouge), `Feedback` (tronqué à 100 chars, tooltip au hover).
- **Pagination** : `limit=20&offset=0` (cf. AC s19).
- **Multi-tenant** : la liste est filtrée par le backend (JWT).

#### Dashboard parent (s17)

- **Statistiques** : `<Card>` + `<Chart>` (Recharts) — taux de réussite par exercice, évolution dans le temps. **PAS** d'affichage des réponses elles-mêmes (PII / données élève).

Ces comportements seront **re-validés** dans les stories UI qui les implémenteront. Le design system § « UI patterns imposés » (loading / empty / error / success, lignes 203-210) s'applique.

## Composants du design system référencés (pour info, pas à utiliser ici)

| Composant | Rôle pour les stories en aval |
| --- | --- |
| `<Card>` (header / body / footer) | Conteneur énoncé, verdict, feedback |
| `<Textarea>` | Zone de réponse de l'élève |
| `<Label>` (associé au Textarea) | a11y dès le départ (s12) |
| `<Button>` (primary, secondary, ghost) | « Soumettre », « Réessayer », « Voir la correction » |
| `<Toast>` (success, warning, error) | Notifications verdict |
| `<details>` (HTML natif) | Section repliable « Critères d'évaluation » |
| `<StreamingMessage>` (avec `aria-live="polite"`) | Si la future UI streame la progression du LLM (peu probable pour s07, plus pour s08) |
| `<LanguageSwitcher>` | FR/EN (s11 + s21) |
| `<Table>` | Historique des tentatives (s19) |
| `<Chart>` (via Recharts) | Statistiques de réussite (s16, s17) |
| `<Avatar>` | Attribution exercices (s17) |

## Gaps du design system pour cette story

**Aucun gap bloquant pour cette story** (puisque la story ne consomme pas le design system).

**Gaps prévisibles pour les futures stories UI** (à anticiper, pas à résoudre ici) :

| Gap | Action future |
| --- | --- |
| **Pattern « disclaimer IA »** | Le DS actuel ne catalogue pas ce pattern. À introduire quand une story UI consomme un verdict LLM. Probablement comme nouveau composant `<AiDisclaimer>` ajouté au DS § Available components. |
| **Composant `<Badge>` verdict (vert/rouge/gris)** | Non listé explicitement. À introduire (probablement importé depuis shadcn/ui). |
| **Pattern « zone de réponse longue » (Textarea + compteur)** | Le DS mentionne `<Input>` mais pas `<Textarea>`. À introduire. |

**Ces gaps ne sont pas à résoudre dans s07** — la story ne touche pas à l'UI. Ils seront adressés au moment où les stories UI qui consomment s07 sont créées.

## Mockup

**Aucun mockup HTML.** Justification : la story n'a pas d'écran. Le `docs/designs/s07-repondre-texte-libre.html` n'est pas créé — sa création serait une violation du contrat ks-design.

Pour les stories futures qui consommeront le grader s07, le mockup sera produit dans :

- `docs/designs/s11-frontend-upload-chat.html` (page /exercises/{id}, si étendu)
- `docs/designs/s19-historique-conversations.html` (historique des tentatives, si exercices inclus)
- `docs/designs/s17-dashboard-parent.html` (statistiques enfant)

## Liens

- `docs/stories.md:262-294` — story s07 complète.
- `docs/research/s07-repondre-texte-libre.md` — recherche (540 lignes, déjà livrée).
- `docs/design-system.md` — design system (catalogue composants, tokens).
- `docs/architecture.md` § Frontend — cadre général.
- `docs/architecture.md:207-217` (schéma `attempts`) — la colonne `answer_text` (String 8192) est pré-créée depuis s04 (ligne 152-155) pour s07.
- `docs/architecture.md:188-205` (schéma `exercises`) — `statement`/`expected_answer`/`grading_criteria` utilisés par s07.
- CLAUDE.md § Correction progressive des Exercices — algorithme détaillé (mais le LLM-as-judge est binaire ici, c'est s08 qui introduit la nuance).
- `docs/architecture.md:188-205` (schéma `exercises`) — `expected_answer` et `grading_criteria` sont les inputs du prompt LLM.
- ADR 003 (langgraph-supervisor) — non applicable.
- ADR 004 (rag-isolation-by-collection) — convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 006 (frontend-nextjs-app-router) — cadre i18n + a11y pour les futures stories UI.

## Pré-requis pour passer à `/ks-plan`

Aucun gap visuel à trancher. Le plan s07 peut être écrit sans design additionnel. Les décisions ouvertes (D1 structure du prompt, D2 prompt de retry « plus strict », D3 politique de troncature, D4 format du feedback) sont tranchées dans la recherche s07 (section « Décisions d'architecture »).

**Note de couplage** : la recherche s07 listait s06 comme dépendance dure, mais **cette dépendance est désormais satisfaite** : s06 a été squash-mergé (commit f928d65, PR #7) sur `main` le 2026-09-01, livrant `FreeGenerator` qui persiste les `Exercise` de type `probleme` ou `redaction` avec `statement` / `expected_answer` / `grading_criteria` populés. s06b a également mergé (squash 394d4d4, PR #8) ajoutant `FLASHCARDS` à l'enum — s07 doit explicitement **rejeter** les `FLASHCARDS` (cf. décision D2.a étendue) car les flashcards sont un outil d'étude, pas un exercice noté (note design s06b). 

Le plan s07 doit donc :

- **Faire un rebase** sur `origin/main` au début de la branche (étape 0 du plan) pour intégrer s05, s06 et s06b.
- S'appuyer sur l'interface s06 effective : `Exercise.statement` / `expected_answer` / `grading_criteria` non-NULL pour `PROBLEME` et `REDACTION`. Tester avec un stub `Exercise` qui simule les deux types acceptés (`probleme` et `redaction`) **et** les deux types rejetés (`qcm` et `flashcards`).
- Documenter dans le commit message que s07 complète la boucle de génération-correction pour les exercices libres (s06 produit → s07 grade), sans toucher aux QCM (s03/s04) ni aux flashcards (s06b).
