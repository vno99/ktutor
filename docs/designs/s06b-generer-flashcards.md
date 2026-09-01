---
name: design-s06b-generer-flashcards
description: s06b-generer-flashcards — la story est purement backend, aucun écran à concevoir. La nuance : les flashcards sont un outil d'étude, pas un exercice noté — l'UI de révision est très différente de l'UI d'exercice.
metadata:
  type: project
  story: s06b-generer-flashcards
---

# Design — Story s06b-generer-flashcards

> **Aucun écran à produire.** Cette story est purement backend (générateur LLM de flashcards, persistance PostgreSQL). Tous les acceptance criteria portent sur la CLI, la couche de service, ou les tests. Aucun composant du design system n'est consommé.

## Rappel de la story

**As an** élève **I want** générer des flashcards (recto : question, verso : réponse) à partir d'un de mes documents **so that** je puisse réviser par rappel actif.

**Complexity** : 3 — LLM generation + structured output + persistence.

**Split history** : s06b a été séparée de l'ancien s06 (qui couvrait `probleme|redaction|flashcards`) pour respecter le périmètre PRD : les flashcards sont un **type d'exercice à part entière**, pas une option des exercices libres. Voir `docs/reviews/stories.md` § Corrections issues de la review.

**Différence fondamentale avec s06** : les flashcards ne sont **PAS** un exercice noté. Le notes `docs/stories.md:252` sont explicites : « For the POC, flashcards are NOT graded via the progressive correction flow (s08) — they are a study aid, not an evaluated exercise. » L'UI de révision (carte recto-verso avec auto-évaluation binaire « su / pas su ») est très différente de l'UI d'exercice QCM/problème/rédaction.

### Acceptance criteria (résumé)

| AC | Surface | Type |
| --- | --- | --- |
| AC1 | CLI : `generate-flashcards --n 10` | **CLI flag** (typer) |
| AC2 | JSON valide, parseable | **Sortie JSON structurée** |
| AC3 | Cards ancrées sur le `document_id` (chunks filtrés) | **Logique backend** |
| AC4 | `front` self-contained, `back` concise (≤ 200 chars) | **Contraintes de validation Pydantic** |
| AC5 | Persistance `Exercise` (polymorphique par `type='flashcards'`) | **Backend service** |
| AC6 | Test schéma JSON valide (front, back, topic non-vides) | **Test** |
| AC7 | Test cross-tenant `pseudo_a`/`pseudo_b` | **Test** |

**Aucune surface UI/Web.** Le générateur sera déclenché par la CLI (`backend/app/cli.py`) ou par une future API REST (s09-s11).

## Pourquoi pas de design

Règle du contrat ks-design (lignes du skill) :

> **Vous êtes INTERDIT de** :
> - Produire un design sans design system existant.
> - Inventer un composant, token, couleur ou espacement en dehors du design system.
> - Concevoir un écran que la story ne demande pas.

Cette story ne demande aucun écran. Produire un mockup HTML ici violerait la troisième interdiction.

## Écrans futurs qui consommeront l'API s06b

Le générateur de s06b sera consommé visuellement par les stories UI suivantes, **pas avant** :

| Écran | Story | Composants DS consommés | Notes |
| --- | --- | --- | --- |
| `/exercises/new` (page de génération, section flashcards) | **s11-frontend-upload-chat** (extension) | `<Select>` (type), `<Input>` (n), `<Button>` (générer), `<Card>` (deck généré) | Similaire à l'écran de génération QCM et exercices libres (s06) |
| `/exercises/{id}/study` (mode révision flashcard) | **Story UI dédiée après s11** (non encore dans `docs/stories.md` — à créer) | `<Card>` (recto), `<Button>` (retourner), `<Card>` (verso), `<Button>` (su / pas su / difficile), `<Progress>` (carte N/total) | **UI très spécifique** : mode révision avec auto-évaluation binaire. **Pas d'input texte** de la part de l'élève. |
| `/dashboard/eleve` (statistiques de révision) | **s16-dashboard-eleve** (extension) | `<Card>`, `<Chart>` (Recharts) | Compteur de cartes révisées, taux de réussite par carte, etc. |
| Liste des decks par document | **s11** (extension `/documents`) ou **s19** (historique) | `<Table>`, `<Card>`, `<Avatar>` | « Mes decks de flashcards » par document uploadé |

**Aucun de ces écrans n'est dans le périmètre de s06b.** Ils seront conçus au moment de leur story respective via `/ks-design <story>`, qui lira **ce document** pour comprendre le contrat de sortie du générateur.

**Note importante** : l'écran principal de consommation (`/exercises/{id}/study`) n'est **pas encore** dans `docs/stories.md` au-delà de l'évocation. C'est une story à part entière qui viendra après s11. Le plan s06b doit livrer une API **propre** (contrat JSON stable, persistance fiable) pour ne pas bloquer cette future story UI.

## Contrat de sortie à fixer pour les stories en aval

Bien que s06b ne produise pas d'écran, le contrat de sortie du `FlashcardGenerator` est **imposé** aux futures stories UI. Documenter ici pour qu'elles le respectent sans réinventer.

### Format JSON (CLI → future UI)

```typescript
type FlashcardDeck = {
  exercise_id: string;            // UUID v4
  type: "flashcards";             // discriminant
  subject: "maths" | "francais";
  document_id: string;            // UUID du document source
  cards: Array<{
    front: string;                // question, 1-200 chars
    back: string;                 // réponse concise, 1-200 chars
    topic: string | null;         // optionnel, non-vide si présent
  }>;
  created_at: string;             // ISO 8601, UTC
};
```

### Comportement UI attendu (à implémenter dans les stories futures)

#### Écran de génération (extension de s11)

- **Champ nombre** : `<Input type="number" min="1" max="30">` avec `<label htmlFor="n">`. Défaut `10`. Pas de slider — input numérique simple.
- **Validation** : `n` doit être dans `[1, 30]`, sinon `aria-invalid="true"` + message d'erreur inline (« Nombre de cartes entre 1 et 30 »).
- **Bouton** : `<Button variant="primary">` « Générer le deck ». `disabled` tant que `n` est invalide OU `document_id` n'est pas sélectionné.
- **État de chargement** : 3 points animés (cf. design system ligne 221) sur le bouton, `aria-busy="true"`, latence typique LLM 5-15s.
- **État d'erreur** : `<Toast>` rouge 4s (`role="status"`), bouton « Réessayer » qui re-tente avec les mêmes paramètres.
- **État de succès** : le deck apparaît dans une `<Card>` avec animation subtile (fade-in 200ms, respect `prefers-reduced-motion`). Compteur « 10 cartes générées » en `text-text-secondary` au-dessus.

#### Écran de révision (story UI dédiée, futur)

- **Layout** : `<Card>` plein écran avec une seule carte visible. Au-dessus : `<Progress>` (barre fine 4px, `bg-primary`) « 3 / 10 ».
- **Recto** : face avant, `text-lg` centré, padding généreux (32px). `<Button variant="ghost">` « Retourner » en bas.
- **Verso** : retourné par tap/clic sur la carte OU sur le bouton. `text-base` sur fond `bg-surface-subtle` (contraste subtil). `<Button variant="primary">` « Su », `<Button variant="secondary">` « Difficile », `<Button variant="ghost">` « Pas su » en bas.
- **Animation de retournement** : flip 3D (rotateY 180deg) 400ms. **Respect strict de `prefers-reduced-motion`** : pas de flip si activé, simple bascule de fond.
- **Auto-évaluation** : stockée en local (Zustand) + sync backend (table `FlashcardReview` à créer). Pas de correction LLM — l'auto-évaluation est l'événement d'apprentissage.
- **Multi-tenant** : côté UI, le `pseudo` vient du JWT (s12) — la UI ne le demande jamais.

Ces comportements seront **re-validés** dans les stories UI qui les implémenteront. Le design system § « UI patterns imposés » (loading / empty / error / success, lignes 203-210) s'applique.

## Composants du design system référencés (pour info, pas à utiliser ici)

| Composant | Rôle pour les stories en aval |
| --- | --- |
| `<Select>` (natif) | Sélecteur de document source |
| `<Input>` (number) | Champ « nombre de cartes » (1-30) |
| `<Label>` (associé à chaque input) | a11y dès le départ (s12) |
| `<Button>` (primary, secondary, ghost) | « Générer », « Retourner », « Su / Difficile / Pas su » |
| `<Card>` (header / body / footer) | Conteneur du deck / de la carte |
| `<Toast>` (success / error) | Notifications de succès/échec |
| `<LanguageSwitcher>` | FR/EN (s11 + s21) |
| `<Progress>` (barre fine) | Compteur « 3 / 10 » en révision |
| `<Avatar>` | Attribution decks par document (s17) |
| `<Table>` | Liste des decks (s19) |
| `<Chart>` (via Recharts) | Statistiques de révision (s16) |

## Gaps du design system pour cette story

**Aucun gap bloquant pour cette story** (puisque la story ne consomme pas le design system).

**Gaps prévisibles pour la future story UI de révision** (à anticiper, pas à résoudre ici) :

| Gap | Action future |
| --- | --- |
| **Composant `<Card>` retournable (flip 3D)** | Le DS actuel ne catalogue pas ce pattern. À introduire quand la story UI de révision est planifiée — probablement comme nouveau composant `<Flashcard>` ajouté au DS § Available components. |
| **Composant `<Progress>` (barre fine)** | Non listé dans le DS. À introduire ou à importer depuis shadcn/ui (`@radix-ui/react-progress`). |
| **Pattern d'auto-évaluation binaire (3 boutons Su/Difficile/Pas su)** | Nouveau pattern. À documenter dans le DS § UI patterns. |

**Ces gaps ne sont pas à résoudre dans s06b** — la story ne touche pas à l'UI. Ils seront adressés au moment où la story UI de révision sera créée.

## Mockup

**Aucun mockup HTML.** Justification : la story n'a pas d'écran. Le `docs/designs/s06b-generer-flashcards.html` n'est pas créé — sa création serait une violation du contrat ks-design.

Pour les stories futures qui consommeront le générateur s06b, le mockup sera produit dans :

- `docs/designs/s11-frontend-upload-chat.html` (page /exercises/new étendue, section flashcards)
- `docs/designs/s19-historique-conversations.html` (si « Mes decks » est inclus)
- `docs/designs/<future>-flashcard-study.html` (écran de révision dédié — story pas encore créée)

## Liens

- `docs/stories.md:223-258` — story s06b complète.
- `docs/research/s06b-generer-flashcards.md` — recherche (livrée à l'instant, ~500 lignes attendues).
- `docs/design-system.md` — design system (catalogue composants, tokens).
- `docs/architecture.md` § Frontend — cadre général.
- ADR 003 (langgraph-supervisor) — non applicable.
- ADR 004 (rag-isolation-by-collection) — convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 006 (frontend-nextjs-app-router) — cadre i18n + a11y pour les futures stories UI.
- `docs/stories.md:1073-1076` (notes de review) — justification du split s06 / s06b.
- `docs/architecture.md:188-205` (schéma `exercises` polymorphe) — la colonne `cards` (JSON) doit être ajoutée par s06b (cf. recherche s06b § Décision D1).

## Pré-requis pour passer à `/ks-plan`

Aucun gap visuel à trancher. Le plan s06b peut être écrit sans design additionnel. Les 6 décisions ouvertes (D1 schéma `cards` vs réutilisation, D2 ordre de merge vs s06, D3 déduplication des fronts, D4 longueur 200 chars, D5 default 10/max 30, D6 `topic: str | None`) sont tranchées dans la recherche s06b (section « Décisions d'architecture »).

**Note de collision** : s06b et s06 modifient le même fichier `models.py` (ajout à `ExerciseType`). La recherche s06b recommandait que s06b merge en premier, mais **cette recommandation est désormais obsolète** : s06 a déjà été squash-mergé (commit f928d65, PR #7) sur `main` le 2026-09-01, ajoutant `PROBLEME` et `REDACTION` à l'enum. Au moment où s06b sera implémentée, l'enum contiendra déjà 3 valeurs (`QCM`, `PROBLEME`, `REDACTION`) et s06b ajoutera `FLASHCARDS` (union triviale de 4 valeurs au final). Le plan s06b doit :

- **Faire un rebase** sur `origin/main` au début de la branche (étape 0 du plan) pour intégrer s05 et s06.
- Importer `extract_json_block` depuis le module `_parsing.py` créé par s06 (mutualisation), pas redéfinir ni dupliquer.
- Ajouter la commande `generate_flashcards` dans `cli.py` à côté de `generate_exercise` (s06), pas de collision.
- Documenter dans le commit message que s06b complète la famille d'exercices (QCM + probleme + redaction + flashcards).
