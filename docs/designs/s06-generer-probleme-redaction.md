---
name: design-s06-generer-probleme-redaction
description: s06-generer-probleme-redaction — la story est purement backend, aucun écran à concevoir. Référence vers s11 et s16 pour les écrans qui consommeront le résultat.
metadata:
  type: project
  story: s06-generer-probleme-redaction
---

# Design — Story s06-generer-probleme-redaction

> **Aucun écran à produire.** Cette story est purement backend (générateur LLM de problèmes / rédactions, persistance PostgreSQL). Tous les acceptance criteria portent sur la CLI, la couche de service, ou les tests. Aucun composant du design system n'est consommé.

## Rappel de la story

**As an** élève **I want** générer un exercice de type problème (maths) ou rédaction (français) **so that** je puisse m'entraîner sur un exercice libre.

**Complexity** : 3 — LLM generation + structured output + persistence.

### Acceptance criteria (résumé)

| AC | Surface | Type |
| --- | --- | --- |
| AC1 | CLI : `generate-exercise --type probleme\|redaction --topic ... --difficulty facile\|moyen\|difficile` | **CLI flag** (typer) |
| AC2 | Format `probleme` (énoncé multi-étapes + données numériques) | **Sortie JSON structurée** |
| AC3 | Format `redaction` (sujet + longueur + registre imposés) | **Sortie JSON structurée** |
| AC4 | Persistance `Exercise` (polymorphique par `type`) | **Backend service** |
| AC5 | Test schéma JSON valide pour les 2 types | **Test** |

**Aucune surface UI/Web.** Le générateur sera déclenché par la CLI (`backend/app/cli.py`) ou par une future API REST (s09-s11).

## Pourquoi pas de design

Règle du contrat ks-design (lignes du skill) :

> **Vous êtes INTERDIT de** :
> - Produire un design sans design system existant.
> - Inventer un composant, token, couleur ou espacement en dehors du design system.
> - Concevoir un écran que la story ne demande pas.

Cette story ne demande aucun écran. Produire un mockup HTML ici violerait la troisième interdiction.

## Écrans futurs qui consommeront l'API s06

Le générateur de s06 sera consommé visuellement par les stories UI suivantes, **pas avant** :

| Écran | Story | Composants DS consommés |
| --- | --- | --- |
| `/exercises/new` (page de génération d'exercice) | **s11-frontend-upload-chat** (extension naturelle) ou **story dédiée après s11** | `<Select>` (type, matière, difficulté), `<Input>` (topic), `<Button>` (générer), `<Card>` (énoncé généré) |
| `/exercises/{id}` (page de réponse à un exercice) | **s11** + **s08** (correction progressive) | `<StreamingMessage>` (énoncé progressif), `<Textarea>` (saisie réponse), `<Card>` (correction) |
| `/dashboard/eleve` (liste des exercices tentés) | **s16-dashboard-eleve** | `<Table>`, `<Card>`, `<Tabs>` (par matière/type) |
| Évaluation copy-of-exam | **s18** (évaluations) | `<FileUpload>` (image copie), `<Card>` (score) |

**Aucun de ces écrans n'est dans le périmètre de s06.** Ils seront conçus au moment de leur story respective via `/ks-design <story>`, qui lira **ce document** pour comprendre le contrat de sortie du générateur libre.

## Contrat de sortie à fixer pour les stories en aval

Bien que s06 ne produise pas d'écran, le contrat de sortie du `FreeExerciseGenerator` est **imposé** aux futures stories UI. Documenter ici pour qu'elles le respectent sans réinventer.

### Format JSON (CLI → future UI)

```typescript
type FreeExercise = {
  exercise_id: string;            // UUID v4
  type: "probleme" | "redaction"; // discriminant
  subject: "maths" | "francais";
  statement: string;              // énoncé (multi-étapes pour probleme, sujet pour redaction)
  expected_answer: string;        // solution complète (utilisée par s07 pour le grading)
  grading_criteria: string[];     // liste de critères pour le grader LLM (s07)
  difficulty: "facile" | "moyen" | "difficile";
  topic: string;                  // sujet/thème (paramètre d'entrée)
  created_at: string;             // ISO 8601, UTC
};
```

### Comportement UI attendu (à implémenter dans les stories futures)

- **Affichage de l'énoncé** : `<Card>` avec `statement` rendu en `font-mono` (JetBrains Mono) si la sortie contient des formules mathématiques (maths), en `font-sans` (Inter) sinon (français). Détection simple : présence de caractères comme `=`, `²`, `→`, ou retour à la ligne + chiffres.

- **Affichage des `grading_criteria`** : section repliable `<details>` (composant natif HTML) sous l'énoncé, label « Critères d'évaluation » (i18n via `next-intl`). Contenu en `text-text-secondary`, `text-sm`. Permet à l'élève de voir comment sa réponse sera notée.

- **Affichage de `expected_answer`** : **JAMAIS visible** à l'élève avant qu'il ait soumis (cf. CLAUDE.md § Correction progressive). C'est `s08-correction-progressive` qui décide quand la révéler.

- **Sélecteurs** (page de génération) :
  - **Type** : `<Select>` natif avec 2 options : « Problème de maths » / « Rédaction de français ». La liste des options dépend de la matière choisie (maths → probleme, français → redaction).
  - **Matière** : `<Select>` natif, « Maths » / « Français ». Le composant `<Select>` (natif, pas custom ARIA) est la convention du design system ligne 167.
  - **Difficulté** : `<Select>` natif à 3 options : « Facile » / « Moyen » / « Difficile ». 3 niveaux visibles — pas de slider.
  - **Topic** : `<Input>` texte (200 chars max), `<label htmlFor="topic">` explicite, `placeholder` « ex: dérivée, lettre de motivation, etc. ».

- **État de chargement** : 3 points animés (`prefers-reduced-motion` respecté) sur le bouton « Générer » qui devient `disabled` + `aria-busy="true"`. Latence typique LLM : 5-15s.

- **État d'erreur** (réseau, LLM timeout, `malformed_output` après retry) : `<Toast>` rouge 4s en haut (`role="status"`), bouton « Réessayer » qui re-tente avec les mêmes paramètres.

- **État de succès** : l'énoncé apparaît dans une `<Card>` avec animation subtile (fade-in 200ms, respect `prefers-reduced-motion`). Le `topic` et la `difficulty` sont rappelés en `text-text-secondary` au-dessus de l'énoncé.

- **Multi-tenant** : côté UI, le `pseudo` vient du JWT (s12) — la UI ne le demande jamais. La liste des exercices de l'élève est filtrée par le backend (cf. ADR 004).

- **Persistance** : pas de bouton « Sauvegarder » séparé — la génération persiste automatiquement (AC4). L'ID retourné permet de naviguer vers `/exercises/{id}` pour répondre.

Ces comportements seront **re-validés** dans les stories UI qui les implémenteront. Le design system § « UI patterns imposés » (loading / empty / error / success, lignes 203-210) s'applique.

## Composants du design system référencés (pour info, pas à utiliser ici)

| Composant | Rôle pour les stories en aval |
| --- | --- |
| `<Select>` (natif) | Sélecteur de type, matière, difficulté |
| `<Input>` (text) | Champ « topic » |
| `<Label>` (associé à chaque input) | a11y dès le départ (s12) |
| `<Button>` (primary) | Bouton « Générer l'exercice » |
| `<Card>` (header / body / footer) | Conteneur pour l'énoncé généré |
| `<Textarea>` | Zone de réponse de l'élève (s07 + s08) |
| `<StreamingMessage>` (avec `aria-live="polite"`) | Affichage incrémental si s11+s09 streame la génération |
| `<Toast>` (success / error) | Notifications de succès/échec |
| `<LanguageSwitcher>` | FR/EN (s11 + s21) |
| `<Tabs>` (par matière) | Dashboard élève s16 |
| `<Table>` | Liste des exercices s19 |
| `<Chart>` (via Recharts) | Dashboard progression s16 |
| `<Avatar>` | Attribution exercices s17 |

## Gaps du design system pour cette story

**Aucun.** La story ne consomme pas le design system.

## Mockup

**Aucun mockup HTML.** Justification : la story n'a pas d'écran. Le `docs/designs/s06-generer-probleme-redaction.html` n'est pas créé — sa création serait une violation du contrat ks-design.

Pour les stories futures qui consommeront le générateur s06, le mockup sera produit dans :

- `docs/designs/s11-frontend-upload-chat.html` (page /chat + /exercises, si étendu)
- `docs/designs/s16-dashboard-eleve.html` (dashboard)
- `docs/designs/s19-historique-conversations.html` (historique, si exercices inclus)
- `docs/designs/s08-correction-progressive.html` (UI de correction — si une story UI dédiée est créée)

## Liens

- `docs/stories.md:190-219` — story s06 complète.
- `docs/research/s06-generer-probleme-redaction.md` — recherche (499 lignes, déjà livrée).
- `docs/design-system.md` — design system (catalogue composants, tokens).
- `docs/architecture.md` § Frontend — cadre général.
- ADR 003 (langgraph-supervisor) — non applicable (s06 = pas d'agent, juste un générateur).
- ADR 004 (rag-isolation-by-collection) — convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 006 (frontend-nextjs-app-router) — cadre i18n + a11y pour les futures stories UI.
- CLAUDE.md § Correction progressive — la `expected_answer` n'est JAMAIS révélée à l'élève avant qu'il ait soumis (s08 gère le dévoilement).

## Pré-requis pour passer à `/ks-plan`

Aucun gap visuel à trancher. Le plan s06 peut être écrit sans design additionnel. Les 6 décisions ouvertes (D1 routing par sous-fonctions, D2 difficulté module le détail, D3-D6 sur le format des champs) sont tranchées dans la recherche s06 (section « Décisions d'architecture »).

**Note de collision** : s06 et s06b modifient le même fichier `models.py` (ajout à `ExerciseType`). Le plan s06 doit préciser l'ordre d'ajout (s06b d'abord, recommandé) pour éviter les conflits de merge — cf. recherche s06 § Pièges.
