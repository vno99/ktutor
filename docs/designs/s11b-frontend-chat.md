# Design — Story s11b-frontend-chat

> Mockup statique de référence : `docs/designs/s11b-frontend-chat.html`. **Ne pas copier en production** — l'implémentation utilise les vrais composants du design system (`frontend/components/`).
> Source unique de vérité visuelle : `docs/design-system.md` (258 lignes, 13 AC validés). Aucun token ou composant inventé ici.

## Screen(s)

**Une seule page** : `/{locale}/chat` (locales `fr` par défaut, `en`).

### Layout (mobile 360 px, puis tablette ≥ 768 px)

- **Container** :
  - Mobile (≤ 768 px) : `px-4 py-4`, full-width, contenu `flex flex-col gap-4`.
  - Tablette (≥ 768 px) : `max-w-3xl mx-auto px-6 py-6`, mêmes gaps.
- **Sections** (de haut en bas) :
  1. **Header sticky 56 px** (réutilise `<Header>` de s11a, lien `/chat` **actif** — `aria-disabled` retiré, lien `/upload` reste `aria-disabled="true"` + ajout de `tabindex="-1"`).
  2. **Titre de page** (`text-2xl md:text-3xl font-semibold tracking-tight`) : « Chatter avec un agent » (FR) / « Chat with an agent » (EN).
  3. **Sélecteur de matière** (`<Select>` du design system, 44 px) : options « Mathématiques » (value `maths`) et « Français » (value `francais`). `<Label>` au-dessus (jamais `srOnly`, le sélecteur est l'élément primaire).
  4. **Champ question** : `<Textarea>` (nouveau composant — gap design system, voir § Gaps) avec `<Label>` au-dessus, hauteur min 4 lignes (`min-h-24`), resize vertical autorisé, `maxLength={2000}`. Compteur `2000` caractères sous la textarea, `text-xs text-text-tertiary`. `<div aria-live="polite" className="sr-only">` qui annonce le compte à rebours quand on passe sous 100 chars restants (i18n `chat.charCountRemaining`).
  5. **Bouton « Envoyer »** : `<Button variant="primary" size="md">` 44×44 px minimum, désactivé tant que (pseudo invalide OU matière vide OU question vide OU `isStreaming`). État désactivé : `aria-disabled="true"` + `tabindex="-1"` + `disabled:opacity-50 disabled:cursor-not-allowed` (auto via Button). Icône Lucide `send` 20 px à gauche du label.
  6. **Zone de stream** : `<StreamingMessage>` (étendu, voir § Reused components). Hauteur min `min-h-32` (laisse de la place pour le typing indicator + 2-3 lignes de réponse). Bordure `border border-border rounded-md p-4 bg-surface`.
  7. **Sous la zone de stream** : ligne « Sources : » rendue conditionnellement si `sources?.length > 0` (texte `text-xs text-text-secondary`, séparée par `·`, max 5 fichiers affichés + « … et N autres » au-delà).
  8. **Card d'erreur inline** (cf. design-system § États) : `<Card>` `bg-error/10 border border-error/30 rounded-md p-4` avec icône Lucide `alert-triangle` 24 px en `text-error`. Masquée par défaut, affichée si `error != null`. Contient un message humain + code machine en `text-xs text-text-tertiary` (cf. design-system l.161) + bouton « Réessayer » (`<Button variant="secondary" size="sm">`).
  9. **Label « pseudo manquant »** (cf. AC7) : affiché en `text-warning text-sm` au-dessus de la zone de stream quand `!pseudo || !isValidPseudo(pseudo)`. Dans ce cas, l'input pseudo du `<Header>` reçoit `aria-invalid="true"` (déjà câblé, juste condition d'affichage à ajouter dans la page).

### États (4 par écran + 1 chargement, design-system l.151-163)

| État | Déclencheur | Pattern |
|---|---|---|
| **Empty** (initial) | Au mount, avant la 1ère question | Sélecteur vide, textarea vide, bouton désactivé. Message d'accueil centré **dans** la zone de stream : « Pose une question à ton agent. » + 2 exemples : « Qu'est-ce qu'une dérivée ? » (maths), « Quelle est la règle du participe passé avec avoir ? » (français). Texte `text-text-secondary text-sm`. |
| **Loading / Streaming initial** | Après clic Envoyer, avant 1er token | `<StreamingMessage>` avec typing indicator 3 points (`animate-pulse` Tailwind, avec `motion-reduce:animate-none` — gap à fixer, voir § Gaps). Les 3 points sont `bg-text-tertiary h-2 w-2 rounded-full`, décalage 0/150/300 ms. `aria-busy="true"` sur le wrapper. |
| **Streaming** | Au moins 1 token reçu | Tokens accumulés en `text-base text-text-primary` (pas de `<p>` par token, sinon flickering). Le typing indicator disparaît dès le 1er token. |
| **Success / Done** | Event `{done: true, sources: [...]}` reçu | Ligne « Sources : » sous la zone de stream. Le bouton Envoyer redevient actif (sauf si la question est vide, cas trivial). L'input pseudo n'est pas invalidé. |
| **Error — code-mappée** | Event `{error, code}` avec `code ∈ {cross_tenant, no_subject, invalid_pseudo, unknown}` | Card d'erreur inline avec message i18n (`chat.errors.{code}`) + bouton « Réessayer ». Le code machine est affiché en `text-xs text-text-tertiary` sous le message. |
| **Error — réseau** | `fetch` throw, `response.status >= 400`, ou `reader.read()` throw avant `done` | Card d'erreur avec message « Erreur réseau. Vérifie ta connexion. » (`chat.errors.network`) + bouton « Réessayer ». Le bouton re-déclenche `send(lastInput)`. |
| **Error — connexion perdue** | `reader.closed` ou `read()` throw **après** au moins 1 token | Card d'erreur avec message « Connexion perdue. Réessayer ? » (`chat.errors.lost`) + bouton « Réessayer ». Les tokens déjà reçus restent visibles (pas de wipe). |
| **Pas de pseudo** | `!useAuthStore.getState().pseudo` OU `!isValidPseudo(pseudo)` | Label « Choisis un pseudo pour commencer » en `text-warning text-sm` au-dessus de la zone de stream. Le bouton Envoyer est désactivé (sans afficher la raison, c'est l'utilisateur qui doit voir le label warning). L'input du header passe en `aria-invalid="true"` (déjà câblé côté Header, propagation à checker en Plan). |

### Responsive — assertions strictes (AC9)

- **360 px** : textarea full-width, bouton Envoyer full-width en dessous (`flex-col`), le `<Header>` masque les liens desktop Chat/Upload, la bottom tab bar (si présente en s16+) les montre — **mais s11b n'a pas de bottom tab bar** (gap design system l.232), donc le menu utilisateur n'est accessible que via les liens desktop (768+). À 360 px, la navigation reste via le toggle de langue + input pseudo.
- **768 px** : page en `max-w-3xl mx-auto`, textarea + bouton côte à côte (`sm:flex-row` ? non — en fait le bouton reste en dessous pour la lisibilité, mais le container est centré et plus large). Les liens desktop du header sont visibles.
- **Pas de scroll horizontal** aux 2 viewports (assertion du test e2e responsive s11a étendu).

## Mockup

`docs/designs/s11b-frontend-chat.html` — mockup HTML statique, **low-fidelity** (pas de CSS complet, juste la structure + tokens Tailwind statiques). Le but est de **communiquer l'intention** (layout, états), pas d'être pixel-perfect. Le mockup est **explicitement exclu** de la production : `ks-execute` construit la page avec les vrais composants (`<Header>`, `<Select>`, `<Textarea>` (nouveau), `<Button>`, `<StreamingMessage>`, `<Card>`).

Le mockup montre les 5 états critiques côte à côte :
1. Empty (initial)
2. Streaming avec typing indicator
3. Streaming tokens accumulés
4. Done avec sources
5. Erreur réseau avec bouton Réessayer

## Reused components (from the design system)

| Composant | Fichier | Usage | Notes |
|---|---|---|---|
| `<Header>` | `frontend/components/Header.tsx` | Sticky 56 px, logo, language switcher, pseudo input | Modification : retirer `aria-disabled="true"` du lien `/chat` (l.81), ajouter `tabindex="-1"` au lien `/upload` (l.86, gap à fixer) |
| `<Select>` | `frontend/components/Select.tsx` | Sélecteur de matière, 44 px | Réutilisé tel quel. Options : `{value: 'maths', label: 'Mathématiques'}` (ou « Mathematics » en EN), `{value: 'francais', label: 'Français'}`. Cf. `backend/app/api/chat/schemas.py:48` — Literal `maths` \| `francais`. |
| `<Label>` | `frontend/components/Label.tsx` | Pour le sélecteur de matière, la textarea, l'input pseudo manquant | Réutilisé tel quel. **Pas de `srOnly`** ici — tous les labels sont visibles (le sélecteur et la textarea sont des éléments primaires). |
| `<Button>` | `frontend/components/Button.tsx` | Bouton « Envoyer » (primary md) et « Réessayer » (secondary sm) | Réutilisé tel quel. Icône Lucide `send` 20 px via prop `leftIcon`. |
| `<Card>` | `frontend/components/Card.tsx` | Card d'erreur (cf. design-system § États, pattern `bg-error/10 border border-error/30`) | Réutilisé tel quel. |
| `<StreamingMessage>` | `frontend/components/StreamingMessage.tsx` | Zone de réponse avec `aria-live` | **Étendu** (cf. § Gaps : gap à fixer en s11b) : props ajoutées `error?: ChatStreamError \| null` et `sources?: SourceCitation[] \| null`, rendu conditionnel de la card d'erreur et de la ligne Sources. Le typing indicator 3 points reste câblé sur `isStreaming && !hasContent`. |
| `<Textarea>` | **À créer dans s11b** | Champ question (1-2000 chars, multi-ligne) | Gap design system : il n'existe pas dans le catalogue actuel. **Décision D2 du research s11b : composant partagé** dans `frontend/components/Textarea.tsx` (réutilisable par s11c pour les descriptions, et par les formulaires d'admin en s17+). API : `forwardRef<HTMLTextAreaElement, TextareaProps>` avec `id: string`, `label: string` (via prop ou via `<Label>` parent — convention `<Label htmlFor>` séparé), `invalid?: boolean`, `maxLength?: number`, `value?: string`, `onChange?: ...`. Hauteur min 4 lignes, classes `min-h-24 rounded-sm bg-surface text-text-primary border focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30`. |
| Lucide icons | `lucide-react` | `send` (Envoyer), `alert-triangle` (erreur), `alert-circle` (warning), `check-circle` (succès) | Cf. design-system § Icônes. |

## i18n — namespace `chat` (et extension de `errors`)

Le namespace `chat: {}` est vide dans `fr.json` et `en.json` (cf. research § 1.5). s11b remplit les clés suivantes (estimation, à confirmer en Plan) :

| Clé | FR | EN |
|---|---|---|
| `chat.title` | Chatter avec un agent | Chat with an agent |
| `chat.subjectLabel` | Matière | Subject |
| `chat.subjectMaths` | Mathématiques | Mathematics |
| `chat.subjectFrancais` | Français | French |
| `chat.questionLabel` | Ta question | Your question |
| `chat.questionPlaceholder` | Pose une question sur ton cours… | Ask a question about your course… |
| `chat.send` | Envoyer | Send |
| `chat.examplesTitle` | Exemples : | Examples: |
| `chat.exampleMaths` | Qu'est-ce qu'une dérivée ? | What is a derivative? |
| `chat.exampleFrancais` | Règle du participe passé avec avoir ? | Past participle rule with avoir? |
| `chat.sourcesLabel` | Sources : | Sources: |
| `chat.sourcesMore` | … et {n} autres | … and {n} more |
| `chat.emptyState` | Pose une question à ton agent. | Ask your agent a question. |
| `chat.pseudoMissing` | Choisis un pseudo pour commencer. | Choose a pseudo to start. |
| `chat.retry` | Réessayer | Retry |
| `chat.charCountRemaining` | {n} caractères restants | {n} characters left |
| `errors.network` | Erreur réseau. Vérifie ta connexion. | Network error. Check your connection. |
| `errors.lost` | Connexion perdue. Réessayer ? | Connection lost. Retry? |
| `errors.cross_tenant` | Cette question concerne un autre élève. | This question belongs to another student. |
| `errors.no_subject` | Matière inconnue. Choisis « Mathématiques » ou « Français ». | Unknown subject. Choose "Mathematics" or "French". |
| `errors.invalid_pseudo` | Pseudo invalide. 3 à 32 caractères (lettres, chiffres, underscore). | Invalid pseudo. 3 to 32 characters (letters, digits, underscore). |
| `errors.unknown` | Une erreur est survenue. Réessaye plus tard. | Something went wrong. Try again later. |

**Note** : le namespace `errors` n'est pas un fallback global — il est dédié aux erreurs du stream. Les erreurs UI génériques (toast, etc.) sont dans un namespace séparé (futur s25).

## Design system gaps

Items **non couverts** par le design system actuel, à traiter en s11b (extension minimale) ou en story ultérieure (s22, s16). **Aucun n'est inventé** — chacun est routé vers une story de修补.

| Gap | Impact en s11b | Décision s11b | Story de修补 |
|---|---|---|---|
| **Pas de `<Textarea>` dans le design system** | Le sélecteur de matière est OK, mais le champ question est une `<textarea>` et il n'y a pas de composant partagé. | **Créer `<Textarea>` dans `frontend/components/Textarea.tsx`** (cf. D2 du research). API calquée sur `<Input>` (forwardRef, 44 px minimum, `invalid`, focus ring, `maxLength`). Réutilisable par s11c et au-delà. | **s11b** (extension minimale) |
| **Pas de `bottom tab bar` mobile** | À 360 px, la navigation Chat/Upload est masquée côté header (s11a a désactivé les liens desktop via `hidden md:flex`). Pas de bottom tab bar pour les révéler. | **Hors-scope s11b** : la page chat est accessible directement par URL ou via le lien du header (visible à 768+). À 360 px, l'utilisateur doit zoomer ou utiliser le menu mobile (à venir). | **s16** (dashboard) ou **s22** |
| **Pas de `<html lang>` dynamique** | Le test e2e (e) bascule la langue via le `<LanguageSwitcher>`, mais `<html lang="fr">` reste codé en dur. Lighthouse `/en/chat` chuterait potentiellement sur ce point. | **Hors-scope s11b** : on étend Lighthouse à `/fr/chat` seulement (cf. AC10). Le test Playwright vérifie que le contenu bascule, pas la balise `<html lang>`. | **s22** ou **s11b'** |
| **Pas de `motion-reduce:animate-none` sur le typing indicator** | Le squelette `StreamingMessage.tsx:46-55` utilise `animate-pulse` Tailwind, qui **devrait** être désactivé par `motion-reduce:animate-none` mais ne l'est pas encore. C'est une régression de l'accessibilité pour les utilisateurs ayant activé `prefers-reduced-motion`. | **Fixer en s11b** : ajouter `motion-reduce:animate-none` sur les 3 points. 1 ligne, dans le scope de l'extension `<StreamingMessage>`. | **s11b** (correctif a11y) |
| **Pas de composant `<Icon>` wrappant Lucide** | On importe `lucide-react` directement. C'est OK pour 4 icônes, mais à 20+ icônes (s16, s17) il faudrait un wrapper pour centraliser la taille (`aria-hidden` par défaut, `aria-label` explicite). | **Hors-scope s11b** : 4 icônes, import direct suffit. | **s16** ou **s22** |
| **Pas de bouton « Stop » sur le stream** | UX : impossible d'interrompre l'agent. | **Hors-scope s11b** : gap explicite (design-system l.241). | **s22** |
| **Pas de skeleton loader sur empty state** | Le message d'accueil est textuel, pas un skeleton. | **Acceptable en s11b** : un message textuel est plus rapide et plus clair qu'un skeleton pour un empty state first-render. | **s22** si on veut un polish |

## Hors-scope explicite (réaffirmé depuis la story)

- **Persistance de l'historique** côté backend → **s19** (`/chat/history`). En s11b, les messages sont cumulés en mémoire dans `chatStore` mais perdus au refresh.
- **Bouton « Stop »** sur le stream → **s22**.
- **Bouton « Régénérer la réponse »** → non prévu dans le PRD actuel.
- **Streaming depuis l'API corrigée s15** (JWT, multi-tenant strict) → refacto trivial du `send` une fois `useAuthStore.pseudo` branché sur le JWT, mais hors-scope ici.
- **Affichage des chunks par paragraphe** (recherche D7) → RAG actuel retourne un seul stream, pas de paragraph-level chunking.
- **`<html lang>` dynamique** → s22 ou s11c.
- **Multi-tenancy testing côté frontend** → le frontend envoie le `pseudo` qu'il a (cookie-backed, ADR 011), le test d'isolation cross-tenant est côté backend (s09).

## Liens

- `docs/stories.md:459-525` — story s11b complète.
- `docs/research/s11b-frontend-chat.md` — recherche de contexte, 5 faits, 13 pièges, 8 questions ouvertes, 5 décisions.
- `docs/design-system.md` — source unique de vérité visuelle (tokens, composants, UI patterns, a11y, i18n, Do/Don't, gaps).
- `docs/architecture.md` § Frontend — stack imposée, route groups, hydration.
- `docs/decisions/011-frontend-pseudo-cookie-pre-jwt.md` — pourquoi le pseudo est en cookie, pas en URL/body.
- `AGENTS.md` § Frontend (l.108-120) — conventions Zustand, API client, identités, i18n, a11y, composants UI.
- `backend/app/api/chat/router.py:64-134` — endpoint SSE consommé.
- `backend/app/api/chat/sse.py:21-30` — format exact des events.
- `backend/app/api/chat/schemas.py:34-77` — body et codes d'erreur.
- `frontend/components/StreamingMessage.tsx` — squelette à étendre.
- `frontend/components/Header.tsx:79-91` — liens desktop à modifier.
