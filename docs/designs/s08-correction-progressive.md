---
name: design-s08-correction-progressive
description: s08-correction-progressive — la story est purement backend, aucun écran à concevoir. Mais la state machine 4 états dicte un contrat UI critique que les futures stories UI doivent respecter.
metadata:
  type: project
  story: s08-correction-progressive
---

# Design — Story s08-correction-progressive

> **Aucun écran à produire.** Cette story est purement backend (state machine de correction progressive, génération LLM d'indices, persistance Attempt). Tous les acceptance criteria portent sur la CLI, la couche de service, ou les tests. Aucun composant du design system n'est consommé directement.
>
> **MAIS** : la state machine 4 états × 2 types d'exercice dicte un **contrat UI critique** que les futures stories UI doivent respecter pour offrir une expérience cohérente. Ce document fige ce contrat en détail (champs JSON, comportement attendu pour chaque état, animations, micro-interactions).

## Rappel de la story

**As an** élève **I want** que la correction soit dévoilée progressivement (indices d'abord, puis solution) **so that** je sois poussé à réfléchir avant de voir la réponse.

**Complexity** : **4** — State machine across attempts + decision logic + persistence + hint generation. Risque explicité dans `docs/stories.md:325`.

**Dépendances amont** : s04 (QCM submission) + s07 (text submission). s08 consomme le verdict `is_success` des deux et applique la state machine.

### Acceptance criteria (résumé)

| AC | Surface | Type |
| --- | --- | --- |
| AC1 | 1er échec → `correction_level: "partial"` + `hints` + `next_steps` | **Logique state machine** |
| AC2 | 2e échec → `correction_level: "partial_attempt_2"` + indices plus précis | **Logique state machine** |
| AC3 | 3e échec → `correction_level: "full_after_attempts"` + solution complète | **Logique state machine** |
| AC4 | Réussite au 1er essai → `correction_level: "full"` + solution + bonus | **Logique state machine** |
| AC5 | State machine déterministe (1 ≤ N ≤ 3) | **Logique pure** |
| AC6 | Tests des 4 états + cas « success first try » (5 tests) | **Test** |
| AC7 | Indices attempt 2 ≠ indices attempt 1 | **Test** |
| AC8 | Test cross-tenant | **Test** |
| AC9 | `attempt_number > 3` → 409 (exercice fermé) | **Logique + test** |

**Aucune surface UI/Web.** La state machine sera déclenchée par les CLI `submit-qcm` (s04) et `submit-text` (s07) — qui passent désormais par `ProgressiveCorrection.evaluate()` au lieu de retourner juste `is_success`.

## Pourquoi pas de design

Règle du contrat ks-design (lignes du skill) :

> **Vous êtes INTERDIT de** :
> - Produire un design sans design system existant.
> - Inventer un composant, token, couleur ou espacement en dehors du design system.
> - Concevoir un écran que la story ne demande pas.

Cette story ne demande aucun écran. Produire un mockup HTML ici violerait la troisième interdiction.

## Écrans futurs qui consommeront la state machine s08

La state machine s08 dictera le comportement UI des écrans suivants :

| Écran | Story | Vue |
| --- | --- | --- |
| `/exercises/{id}` (page de réponse à un exercice) | **s11-frontend-upload-chat** (extension) ou **story dédiée après s11** | Vue 4-états : partial, partial_attempt_2, full, full_after_attempts |
| `/exercises/{id}/closed` (état final après 3 échecs) | **Story UI s08-extension** (pas encore dans `docs/stories.md`) | Vue statique : « Exercice terminé, voici la correction » |

**Aucun de ces écrans n'est dans le périmètre de s08.** Ils seront conçus au moment de leur story respective via `/ks-design <story>`, qui lira **ce document** pour comprendre le contrat de sortie de la state machine.

## Machine à états (diagramme texte)

```
                  ┌─────────────────────────────────────┐
                  │  Pas d'attempt encore (état initial) │
                  └─────────────┬───────────────────────┘
                                │ submit(exercise_id, answer)
                                ▼
                  ┌─────────────────────────────────────┐
                  │  Tentative N=1                       │
                  └─────┬─────────────────────────┬─────┘
                        │                         │
              is_success=true            is_success=false
                        │                         │
                        ▼                         ▼
              ┌──────────────────┐    ┌────────────────────────┐
              │ correction_level │    │ correction_level       │
              │ = "full"         │    │ = "partial"            │
              │ (solution + bonus│    │ (1-3 hints + next_steps│
              │  + full marks)   │    │  + attempt_number=1)   │
              │ + attempt_number=1│   │                        │
              │ CLOSED           │    │ Réessayable (N+1)      │
              └──────────────────┘    └────────┬───────────────┘
                                                 │
                                       submit(answer)
                                                 ▼
                                  ┌──────────────────────────┐
                                  │ Tentative N=2            │
                                  └────┬───────────────┬─────┘
                                       │               │
                            is_success=true   is_success=false
                                       │               │
                                       ▼               ▼
                            ┌──────────────────┐ ┌──────────────────────┐
                            │ "full"           │ │ "partial_attempt_2"  │
                            │ + bonus          │ │ (hints plus précis)  │
                            │ CLOSED           │ │ Réessayable (N+1)    │
                            └──────────────────┘ └────────┬─────────────┘
                                                            │
                                                  submit(answer)
                                                            ▼
                                         ┌──────────────────────────┐
                                         │ Tentative N=3            │
                                         └────┬───────────────┬─────┘
                                              │               │
                                   is_success=true   is_success=false
                                              │               │
                                              ▼               ▼
                                   ┌──────────────────┐ ┌──────────────────────┐
                                   │ "full"           │ │ "full_after_attempts"│
                                   │ + bonus          │ │ (solution complète)  │
                                   │ CLOSED           │ │ 0 point              │
                                   │                  │ │ CLOSED               │
                                   └──────────────────┘ └──────────────────────┘

  N=4+ → 409 Conflict (l'exercice est fermé)
```

## Contrat de sortie par état (à respecter côté UI)

### État 0 — Pas d'attempt (état initial)

L'UI affiche : énoncé + zone de réponse + bouton « Soumettre ».

### État 1 — `partial` (1er échec)

```typescript
type PartialResult = {
  is_success: false;
  feedback: string;               // feedback court du grader (s04 ou s07)
  attempt_number: 1;
  correction_level: "partial";
  hints: string[];                // 1-3 indices
  next_steps: string;             // ex: "Relis le cours sur les dérivées"
};
```

**Comportement UI attendu** :

- **PAS de Toast rouge** (trop dur après un effort).
- **PAS de solution complète visible** — c'est le principe même de la correction progressive.
- **Card « Indices »** : `<Card>` avec bordure gauche 4px `--color-info` (bleu), fond `bg-info/10`. Titre : « 💡 Indices pour t'aider à réfléchir » (emoji OK ici, ce n'est pas de l'UI chrome mais du contenu pédagogique — vérifier l'évolution des règles DS). Contenu : `hints` en `<ul>` simple. Sous les indices : `next_steps` en `text-text-secondary`.
- **Bouton « Réessayer »** : visible, primary. Ouvre la même zone de réponse avec le texte précédent pré-rempli (l'élève peut améliorer).
- **Compteur de tentatives** : « Tentative 1 / 3 » en `text-text-tertiary`, `text-xs`, en haut à droite.
- **Animation d'apparition** : fade-in 200ms sur la card d'indices (respect `prefers-reduced-motion`).

### État 2 — `partial_attempt_2` (2e échec)

```typescript
type PartialAttempt2Result = {
  is_success: false;
  feedback: string;
  attempt_number: 2;
  correction_level: "partial_attempt_2";
  hints: string[];                // 2-3 indices PLUS précis (différents de l'état 1)
  next_steps: string;             // ex: "Concentre-toi sur l'étape 3 de ton calcul"
};
```

**Comportement UI attendu** :

- Identique à l'état 1, MAIS :
  - Les indices sont **plus ciblés** sur l'erreur spécifique (le LLM doit identifier le type d'erreur).
  - Le compteur passe à « Tentative 2 / 3 ».
  - **Tonalité légèrement plus urgente** : `next_steps` peut suggérer de relire une section spécifique, de vérifier une étape précise.
- **PAS d'avertissement de dernière chance** — l'élève ne doit pas se sentir piégé. La règle est « 3 chances », pas « 2 chances restantes ».

### État 3 — `full` (réussite à n'importe quel essai 1 ≤ N ≤ 3)

```typescript
type FullResult = {
  is_success: true;
  feedback: string;
  attempt_number: 1 | 2 | 3;
  correction_level: "full";
  solution: string;               // solution complète
  detailed_correction: string;    // explication étape par étape
  common_mistakes: string;        // erreurs fréquentes à éviter
  bonus_points: number;           // 2 si N=1, 0 sinon (cf. s20 récompenses)
};
```

**Comportement UI attendu** :

- **Toast vert** : « 🎉 Bonne réponse ! » (`role="status"`, 4s). L'emoji 🎉 est OK ici (contenu gamification — le design system autorise l'usage de l'emoji dans le contenu gamifié, sinon proscrit dans l'UI chrome ligne 276).
- **Card « Solution »** : `<Card>` avec bordure gauche 4px `--color-success` (vert), fond `bg-success/10`. Titre : « Solution complète ».
  - Section 1 : `solution` (texte principal).
  - Section 2 : `detailed_correction` (explications).
  - Section 3 : `common_mistakes` repliable `<details>` (erreurs fréquentes).
- **Bouton « Recommencer un exercice similaire »** : visible, primary. Génère un nouvel exercice (s06 ou s03).
- **Badge « +2 points »** si N=1 (gamification corail) : `<span>` avec `bg-accent-warm/15 text-accent-warm px-2 py-1 rounded-xs`. Cf. design system ligne 30 (`--color-accent-warm` réservé à la gamification).
- **Compteur** : « Réussi du premier coup ! » (N=1) ou « Réussi en 2 essais » (N=2) ou « Réussi en 3 essais » (N=3) — `text-text-secondary`.

### État 4 — `full_after_attempts` (3e échec)

```typescript
type FullAfterAttemptsResult = {
  is_success: false;
  feedback: string;
  attempt_number: 3;
  correction_level: "full_after_attempts";
  solution: string;               // solution complète (révélée)
  detailed_correction: string;
  common_mistakes: string;
  message: string;                // ex: "Après 3 tentatives, voici la correction complète"
  bonus_points: 0;                // pas de bonus
};
```

**Comportement UI attendu** :

- **Tonalité empathique, PAS punitive** : la story insiste sur le côté « pousser à réfléchir, pas punir ». Message d'ouverture : « Après plusieurs tentatives, voici la correction complète. C'est en pratiquant qu'on progresse. »
- **Card « Correction complète »** : `<Card>` avec bordure gauche 4px `--color-warning` (orange), fond `bg-warning/10` (orange léger). Titre : « Correction complète ».
  - Section 1 : `message` d'empathie.
  - Section 2 : `solution`.
  - Section 3 : `detailed_correction`.
  - Section 4 : `common_mistakes` (important ici — l'élève peut apprendre de ses erreurs).
- **PAS de badge « 0 points »** (afficher un 0 est inutile et démoralisant).
- **Bouton « Recommencer un exercice similaire »** : visible, primary. C'est la suite logique.
- **Disclaimer discret** : petit texte en `text-text-tertiary`, `text-xs` : « Tu peux revoir tes cours et réessayer sur des exercices similaires. »

### Erreur 409 — `closed` (4e tentative)

```typescript
type ClosedError = {
  status: 409;
  kind: "closed";
  message: string;                // ex: "Exercice terminé après 3 tentatives."
};
```

**Comportement UI attendu** :

- **Toast rouge** : « Cet exercice est terminé. » (`role="status"`, 4s).
- **La zone de réponse devient désactivée** : `<Textarea disabled>`, `<Button disabled>`. Le compteur passe à « Exercice terminé ».
- **Si l'élève n'a jamais vu la solution** (cas rare : il a fait 3 échecs mais l'UI n'a pas affiché la correction complète) : on l'affiche maintenant, comme pour l'état 4.
- **Bouton « Recommencer un exercice similaire »** : primary, toujours disponible.

## Composants du design system référencés (pour info, pas à utiliser ici)

| Composant | Rôle pour les stories en aval |
| --- | --- |
| `<Card>` (header / body / footer) | Conteneur des 4 états (indices, solution, correction complète) |
| `<Textarea>` | Zone de réponse (réutilisée de s07) |
| `<Button>` (primary, secondary, ghost) | « Réessayer », « Recommencer un exercice similaire » |
| `<Toast>` (success, warning, error) | Notifications verdict |
| `<details>` (HTML natif) | Section repliable « Erreurs fréquentes » |
| `<Badge>` (gamification corail) | Badge « +2 points » si N=1 |
| `<LanguageSwitcher>` | FR/EN (s11 + s21) |
| `<Chart>` (via Recharts) | Statistiques de progression (s16, s17) |

## Gaps du design system pour cette story

**Aucun gap bloquant pour cette story** (puisque la story ne consomme pas le design system).

**Gaps prévisibles pour les futures stories UI** (à anticiper, pas à résoudre ici) :

| Gap | Action future |
| --- | --- |
| **Pattern « 4 états de correction »** (card variants) | Le DS actuel ne catalogue pas ce pattern. À introduire quand la story UI s08-extension est planifiée. Probablement comme 4 variants du composant `<CorrectionCard>` ajoutés au DS § Available components. |
| **Compteur de tentatives** (« 1 / 3 ») | Le DS ne catalogue pas ce pattern. À introduire (probablement importé depuis shadcn/ui). |
| **Badge gamification « +2 points »** | Le DS n'a pas de `<Badge>` explicite. À introduire (probablement importé depuis shadcn/ui avec couleur corail custom). |
| **Animation d'apparition des indices** (fade-in) | Le DS ne catalogue pas les animations de contenu. À introduire. |
| **Emoji dans le contenu pédagogique** (💡, 🎉) | Le DS interdit les emojis dans l'UI chrome (ligne 276) mais ne précise pas le contenu. À clarifier : OK ou pas ? **Recommandation : tolérer les emojis dans le contenu pédagogique** (indices, feedback LLM), proscrire dans l'UI chrome. |

**Ces gaps ne sont pas à résoudre dans s08** — la story ne touche pas à l'UI. Ils seront adressés au moment où les stories UI qui consomment s08 sont créées.

## Mockup

**Aucun mockup HTML.** Justification : la story n'a pas d'écran. Le `docs/designs/s08-correction-progressive.html` n'est pas créé — sa création serait une violation du contrat ks-design.

Pour les stories futures qui consommeront la state machine s08, le mockup sera produit dans :

- `docs/designs/s11-frontend-upload-chat.html` (page /exercises/{id}, si étendu)
- `docs/designs/<future>-correction-progressive.html` (story UI dédiée à la correction progressive — pas encore créée)

## Pièges UX à éviter dans les futures stories UI

Ces pièges sont documentés ici car **la state machine s08 contraint l'UI** :

1. **Ne jamais afficher la solution complète en `partial`** — c'est le principe même de la correction progressive. Si la solution apparaît, la state machine est cassée.

2. **Ne jamais donner l'impression d'être « à court de tentatives »** dans l'état `partial_attempt_2` — l'élève ne doit pas se sentir piégé. Pas de « Plus qu'une chance ! ».

3. **Ne pas afficher de score/points négatifs en `full_after_attempts`** — l'absence de bonus suffit. Afficher « 0 points » est démoralisant.

4. **Le disclaimer IA** (cf. s07 design) doit aussi apparaître en `partial` et `partial_attempt_2` : « L'appréciation est fournie par l'IA. »

5. **L'animation d'apparition des indices ne doit pas être intrusive** : fade-in 200ms max, pas de slide-in, pas de pulse. Le contenu pédagogique doit rester sobre.

6. **La couleur de bordure** doit être cohérente avec le ton :
   - `info` (bleu) pour les indices (neutre, encourageant)
   - `success` (vert) pour la réussite
   - `warning` (orange) pour la correction après échecs (empathique, pas alarmant)
   - `error` (rouge) UNIQUEMENT pour les erreurs techniques (réseau, 409), JAMAIS pour un verdict pédagogique.

## Liens

- `docs/stories.md:297-334` — story s08 complète.
- `docs/research/s08-correction-progressive.md` — recherche (560 lignes, déjà livrée).
- `docs/design-system.md` — design system (catalogue composants, tokens, **couleurs sémantiques**).
- `docs/architecture.md` § Frontend — cadre général.
- `docs/architecture.md:207-217` (schéma `attempts`) — la colonne `correction_level` (String 32, nullable) est pré-créée depuis s04 (ligne 152-155) pour s08.
- CLAUDE.md § Correction progressive des Exercices — algorithme détaillé (note : le CLAUDE.md parle de 5 états, la story en retient 4. Divergence documentée dans la recherche s08 § Pièges — l'état `full_after_attempts` est le 4e état de la story, le CLAUDE.md le compte différemment).
- `docs/stories.md:325` — risque de complexité 4 documenté.
- `docs/prd.md:85` — question ouverte n°2 du PRD (politique « raté vs réussi après aide ») tranchée dans la recherche s08 § Décisions D3.
- ADR 003 (langgraph-supervisor) — non applicable.
- ADR 004 (rag-isolation-by-collection) — convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 006 (frontend-nextjs-app-router) — cadre i18n + a11y pour les futures stories UI.

## Pré-requis pour passer à `/ks-plan`

Aucun gap visuel à trancher. Le plan s08 peut être écrit sans design additionnel. Les 8 décisions ouvertes (D1 state machine en pure function, D2 location des types partagés, D3 politique « raté vs réussi après aide », D4 contenu des prompts d'indices, D5 endpoint unifié vs extensions, D6 bonus points, D7 structure des indices, D8 hints LLM) sont tranchées dans la recherche s08 (section « Décisions d'architecture »).

**Note critique** : la recherche s08 signale un écart entre CLAUDE.md (5 états : `partial`, `partial_attempt_2`, `partial_attempt_3`, `full`, `full_after_attempts`) et la story (4 états : `partial`, `partial_attempt_2`, `full`, `full_after_attempts`). Le plan s08 doit acter la **version 4 états** (celle de `docs/stories.md`) et la documenter dans le commit message pour éviter toute confusion.
