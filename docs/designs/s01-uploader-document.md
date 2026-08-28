# Design — Story s01-uploader-document

> Date : 2026-08-28. Workspace : `.worktrees/s01-uploader-document`.
> Périmètre : expérience CLI (`python -m ktutor.cli upload …`). Pas d'écran UI.

## Screen(s)

La story s01 ne livre **aucun écran UI**. Son interface utilisateur est la ligne de commande : un terminal où l'élève (ou un admin / testeur) tape :

```
python -m ktutor.cli upload ./cours_derivation.pdf --pseudo ali --subject maths
```

Cette commande est **l'interface** de la story. Le « design » porte donc sur :

1. **Le contrat de la commande** (forme exacte des arguments, codes retour, messages).
2. **Le rendu visuel de la sortie terminal** (couleurs, icônes, format, verbosité).
3. **Les états observables par l'utilisateur** (idle, uploading, indexed, error).

Le terminal étant une surface, il a une UX — et cette UX est régie par le design system. Les tokens (couleurs `success` / `error` / `warning`, typographie `mono`) et les patterns (états loading/empty/error/success) s'appliquent.

## Mockup

`docs/designs/s01-uploader-document.html` — mockup statique d'un terminal stylisé affichant les 5 états observables de la commande. Faible fidélité. But : valider les couleurs, l'iconographie (✓ / ✗ / ⚠) et la structure des messages. À ne pas copier dans la prod : la vraie sortie sera générée par `rich` (cf. « Tech mapping »).

## Reused components (from the design system)

| Token / pattern | Usage CLI | Valeur |
|---|---|---|
| **Mono** (`font-mono`) | Toute la sortie terminal | `JetBrains Mono` |
| **`--color-success`** | Ligne de succès, `✓` | `#16A34A` (light) / `#22C55E` (dark) |
| **`--color-error`** | Ligne d'erreur, `✗` | `#DC2626` (light) / `#EF4444` (dark) |
| **`--color-warning`** | Ligne d'avertissement, `⚠` (ex. `manual_review_needed`) | `#D97706` (light) / `#F59E0B` (dark) |
| **`--color-text-secondary`** | Légendes, compteurs, timings | `#5B6472` (light) / `#9AA3B2` (dark) |
| **`--color-accent-warm`** | Total de chunks indexés (récompense visuelle) | `#FF6B4A` (light) / `#FF8B6F` (dark) |
| Pattern « Feedback (toast/inline) » | `print` console : `✓` success + détail | Inline par ligne |
| Pattern « Loading » | Indicateur de progression (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) | Spinner simple |
| Pattern « Empty / Error / Success » | Voir « States » | — |

Pas de composants UI à réutiliser (pas de `<Button>`, pas de `<Input>`) — la sortie est textuelle.

## States (5 états observables)

### 1. `idle` (avant lancement)

```
python -m ktutor.cli upload <file> --pseudo <p> --subject <s>
```

L'utilisateur tape, le shell attend. Pas de retour applicatif.

### 2. `uploading` (pendant le traitement)

```
⠋ Lecture de ./cours_derivation.pdf (3.2 Mo)…
⠋ Extraction du texte (PyMuPDF)…
⠙ OCR (LLM vision)…          (uniquement si image ou PDF scanné)
⠹ Découpage en chunks (RecursiveCharacterTextSplitter, 1000/200)…
⠸ Vectorisation (FastEmbed, 384 dims)…
⠼ Indexation dans ChromaDB (collection rag_maths_ali)…
⠴ Insertion de la row Document en PostgreSQL…
```

Spinner simple, ligne par ligne, pas de barre de progression. Chaque étape reste affichée après fin (log lisible).

### 3. `success`

```
✓ Document indexé avec succès

  Fichier        : ./cours_derivation.pdf
  Pseudo         : ali
  Matière        : maths
  Collection     : rag_maths_ali
  Chunks         : 87
  Embedding dim  : 384
  Document ID    : 7a3c1f2e-4b5d-4e8a-9c1b-2d3e4f5a6b7c
  Durée          : 4.2 s

✓ 10 points ajoutés au profil.
```

### 4. `error` (fichier > 20 Mo, format inconnu, etc.)

```
✗ Échec de l'upload

  Fichier : gros_cours.pdf
  Raison  : taille 24.7 Mo supérieure à la limite (20 Mo)

Code de sortie : 2
```

OU

```
✗ Échec de l'upload

  Fichier : scan_sombre.png
  Raison  : impossible d'extraire du texte (PDF scanné + OCR indisponible)

  Vérifiez que LLM_PROVIDER est configuré et que OPENAI_API_KEY (ou équivalent vision) est défini.

Code de sortie : 3
```

### 5. `manual_review_needed` (OCR manuscrit à faible confiance)

```
⚠ Indexation partielle — révision manuelle requise

  Fichier       : exercice_manuscrit.jpg
  Matière       : maths
  Chunks        : 0
  Confiance OCR : 0.32 (seuil 0.50)

  La copie manuscrite n'a pas pu être transcrite avec une confiance suffisante.
  Aucun document n'a été persisté. Pour réessayer, améliore la qualité de la photo.

Code de sortie : 0  (succès partiel, document NON persisté)
```

**Note** : `code de sortie 0` parce que la commande s'est exécutée correctement et a refusé proprement. C'est l'AC4 « persists nothing » qui est respecté.

## Tech mapping (comment la sortie sera produite)

| Élément visuel | Bibliothèque Python | Justification |
|---|---|---|
| Spinner | `rich.console.Console.status()` | API standard pour les spinners CLI en Python |
| Couleurs vert / rouge / orange | `rich.console.Console.print(style=...)` | Respect des tokens du design system (light ET dark via `color_system="truecolor"`) |
| Monospace | `Console` (par défaut) | Le shell est mono par essence |
| Icônes ✓ ✗ ⚠ | Caractères Unicode directs | Pas de dépendance, lisible sur tous les terminaux UTF-8 |
| Codes retour | `sys.exit(0)` / `sys.exit(N)` | Convention POSIX |
| CLI elle-même | `typer` (recommandé) | Plus moderne que `click`, intégration Pydantic, autocomplétion shell, docstring auto-générée |

`rich` est léger (~200 KB) et déjà dans l'écosystème Python courant. À ajouter à `backend/requirements.txt`.

## Conventions CLI imposées

- **Codes de sortie documentés** :
  - `0` : succès (y compris `manual_review_needed` car l'AC4 « persists nothing » est respecté).
  - `1` : erreur générique (exception non capturée).
  - `2` : fichier trop gros (> 20 Mo) ou format non supporté.
  - `3` : échec OCR (LLM vision indisponible ou transcription vide).
  - `4` : erreur d'écriture ChromaDB ou PostgreSQL.
  - `5` : erreur d'isolation multi-tenant (pseudo ou matière invalide).

- **Format de la sortie** :
  - Première ligne : `✓` / `✗` / `⚠` + un résumé court.
  - Bloc d'indentation 2 espaces avec paires `clé : valeur` (alignement `:` à la même colonne).
  - Une ligne vide avant le code de sortie (en cas d'erreur).
  - Pas de couleur en sortie pipe (auto-détection de `rich.Console` via `force_terminal=None`).

- **Validation des arguments** :
  - `--pseudo` validé par regex `^[a-zA-Z0-9_]{3,32}$`. Erreur 5 si invalide, avec un message d'aide.
  - `--subject` validé contre la liste `["maths", "francais"]` (extensible).
  - `<file>` doit exister. Erreur 2 si absent.
  - Taille vérifiée avant tout traitement lourd.

- **Verbosity** :
  - Par défaut : tout le déroulé (état `uploading`).
  - `--quiet` : n'affiche que la ligne finale ✓/✗/⚠.
  - `--json` : sortie en JSON (utile pour les tests et l'automatisation). Cf. AC5 qui mandate un « documented non-zero code with a message » — le mode JSON est ce qui rend la sortie scriptable.

## Design system gaps

Aucun gap bloquant. Les tokens `success` / `error` / `warning` / `text-secondary` / `accent-warm` couvrent les 5 états observables.

Points d'attention pour une story future (s26 « docs utilisateur » par exemple) :

- Pas de capture d'écran du terminal dans `docs/user-guide/` — il faudra un script qui rejoue la sortie sur un terminal de référence.
- L'auto-détection `light/dark` de `rich` ne marche que si le terminal annonce correctement son thème. À documenter pour les utilisateurs de Windows Terminal (qui supporte le thème via OSC).

## Out of scope

- Pas d'interface web (s11).
- Pas de streaming (la commande upload est batch, pas streamé).
- Pas d'auth (le `--pseudo` est trusted en s01, l'auth arrive en s13).
- Pas de re-upload incrémental (s01 remplace, n'incrémente pas).
- Pas de mise à jour de métadonnées du document (s15+).

## Mockup HTML (rendu visuel de référence)

`docs/designs/s01-uploader-document.html` est un mockup statique d'un terminal (façon Linear macOS window) qui affiche les 5 états côte à côte. **Faible fidélité** : le but est de valider les couleurs, la hiérarchie visuelle, l'iconographie. Ne pas copier ce code en prod : la sortie réelle sera `rich`, pas du HTML dans un `<pre>`.
