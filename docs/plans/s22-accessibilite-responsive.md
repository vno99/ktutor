---
validated: yes
---
# Plan — s22-accessibilite-responsive

Branch: `feature/s22-accessibilite-responsive`
Research: `docs/research/s22-accessibilite-responsive.md`
Design: `docs/designs/s22-accessibilite-responsive.md` (référence statique, pas un nouveau écran)

## Target story

S22 audite et corrige l'accessibilité (WCAG 2.1 A) et le responsive (360/768/1280 px) des 4 pages existantes : `/fr/chat` et `/en/chat`, `/fr/upload` et `/en/upload`, `/fr/dashboard/eleve` et `/fr/dashboard/parent`, `/fr/history` et `/en/history`. Pas de nouveau composant, pas de nouveau token — réutilisation du design-system (`docs/design-system.md`).

AC (docs/stories.md l.1057-1065) : Lighthouse Accessibility ≥ 90 sur chat/upload/dashboard/history ; Tab + focus visible ; images `alt` ; contraste ≥ 4.5:1 ; labels associés ; responsive sans scroll horizontal ; Playwright + axe-core 0 critical/serious.

## Tasks (ordered)

1. [x] Vérifier le Playwright config (`frontend/playwright.config.ts`) : ajouter un projet mobile/tablette ou un override viewport dans le test, et intégrer `@axe-core/playwright` (plugin ou appel manuel). Vérifier que `axe-core` est dans `package.json` / `devDependencies`.
2. [x] Créer (ou étendre) le spec Playwright `frontend/e2e/accessibility.spec.ts` : audit axe-core sur `/fr/chat`, `/fr/upload`, `/fr/dashboard/eleve`, `/fr/history` et leurs équivalents EN. Assertions : 0 `critical`, 0 `serious`. Utiliser `page.evaluate` ou le plugin axe-core.
3. [x] Vérifier le responsive : ajouter des assertions de viewport (360px, 768px, 1280px) dans le même spec ou un `responsive.spec.ts`. Vérifier `overflow-x: hidden` au niveau body et pas de scroll horizontal sur chaque page. Vérifier que la bottom tab bar reste visible et que le header ne se chevauche pas.
4. [x] Audit `alt` images : parcourir `frontend/app/**` et `frontend/components/` pour trouver tout `<img>` sans `alt`. Les icônes décoratives (`lucide-react`) doivent avoir `aria-hidden="true"` (déjà présent dans `StreamingMessage`, `FileUpload`, `Header`). Corriger tout `<img>` manquant.
5. [x] Audit contraste : vérifier si `text-text-tertiary` (`#8B95A3`) est utilisé sur `bg-surface-subtle` (`#F4F6FA`) n'importe où dans le code front. Si oui, corriger (changer la couleur du texte ou du fond) — ne pas inventer de nouveau token, utiliser un token existant du design-system.
6. [x] Vérifier le focus visible : vérifier que chaque bouton (`Button`), chaque lien (`Link`), chaque input (`Input`, `Select`), chaque drop zone (`FileUpload`) a `focus-visible:ring-2 focus-visible:ring-primary/30` et que `outline: none` n'est présent que lorsqu'il est remplacé par `focus-visible:ring-*`. Vérifier dans `globals.css` et dans chaque composant.
7. [x] Vérifier `label htmlFor` : chaque `Input`, `Select`, `FileUpload` doit avoir un `<Label htmlFor={...}>`. Vérifier que `srOnly` est utilisé correctement (jamais absent, jamais visible en doublon). Vérifier `describedBy` sur `FileUpload` et `Select`.
8. [x] Vérifier `aria-disabled` et `tabindex` : le bouton désactivé (ex. bouton Envoyer sans pseudo) doit avoir `disabled` ou `aria-disabled="true"` + `tabindex="-1"`. Vérifier dans `upload/page.tsx` et `chat/page.tsx` (via leurs clients).
9. [x] Vérifier `prefers-reduced-motion` : le `globals.css` a `animation-duration: 0.01ms`. Vérifier que le typing indicator (`StreamingMessage`) et tout autre `animate-pulse` respectent `motion-reduce:animate-none`. Vérifier que le CSS est appliqué correctement dans le navigateur (test manuel Playwright).
10. [x] Vérifier le `lighthouserc.json` : s'assurer que `categories:accessibility` avec `minScore: 0.9` passe réellement. Si le CI n'exécute pas Lighthouse, ajouter un script ou un job CI (hors-scope s22 si pas demandé par l'AC — l'AC demande que le score passe, pas que le CI soit câblé ; mais le test Playwright doit couvrir le même périmètre). Lancer `npx lhci autorun` localement et vérifier le score ≥ 90 sur chaque URL.
11. [x] Vérifier `keyboard navigation` : utiliser Playwright (`keyboard.press('Tab')`) pour naviguer sur chaque page et vérifier que le focus passe par tous les éléments interactifs dans un ordre logique, avec un indicateur visible (`outline` ou `ring`). Vérifier que la drop zone (`FileUpload`) est atteignable au clavier (elle est un `<label htmlFor>` focusable).
12. [x] Vérifier le streaming `aria-busy` et `aria-live` : dans le test Playwright, simuler un stream et vérifier que `aria-busy` passe de `false` à `true` et que le contenu est annoncé via le `role="log"` (pas de vérification directe du screen reader dans Playwright, mais la présence des attributs est vérifiée via `expect(page.locator('[aria-live="polite"]')).toBeVisible()` et `expect(...).toHaveAttribute('aria-busy', 'true')`).

## Run interdicts

- **`progressive.py`** (interdict s08 / AGENTS.md) : ce fichier doit rester inchangé — aucune modification dans le backend. Vérifier que le diff du backend reste vide (sauf si une correction d'accessibilité backend est nécessaire — elle ne l'est pas).
- **Design-system** (`docs/design-system.md`) : ne pas inventer de nouveau composant, token, couleur, espacement. Tout doit réutiliser le design-system existant. Vérifier que le fichier `docs/design-system.md` n'est pas modifié (sauf si un gap est découvert et doit être documenté — mais le design-system est la source de vérité, pas le design de la story).
- **Multi-tenancy** : pas de modification des modèles DB, des collections ChromaDB, du stockage S3. Le code frontend est UI-only ; il ne doit pas toucher `student_pseudo`, JWT, ou isolation. Vérifier que `docs/research/s22-accessibilite-responsive.md` confirme cela.
- **Pas de `localStorage` pour l'identité** (ADR 011) : le `Header` et `useAuthStore` utilisent le cookie `pseudo` (pas `localStorage`). Vérifier que le code reste conforme.
- **Pas de `EventSource` pour SSE** (ADR 006) : le streaming chat utilise `fetch().body.getReader()`. Vérifier que le code reste conforme.
- **Pas d'axios pour le stream** (design-system) : le `StreamingMessage` et le `chatStore` doivent continuer à utiliser `fetch` direct. Vérifier que le code reste conforme.

## The point everything turns on

Le point tournant est le **test Playwright avec axe-core** (tâche 1 et 2). Si `axe-core` n'est pas installé dans le projet, ou si le plugin `@axe-core/playwright` n'est pas compatible avec la version actuelle, le plan doit s'adapter (appel manuel dans le spec au lieu du plugin). Si le Playwright config ne supporte pas de nouveaux projets sans modifier le `webServer`, le responsive doit être testé via `test.use({ viewport })` au lieu d'un projet séparé. La décision (plugin vs manuel, nouveau projet vs override) doit être prise au début du plan et documentée.

Autre point : le score Lighthouse ≥ 90. Si le score actuel est < 90, les correctifs sont des ajustements CSS (contraste, `alt`, focus visible) — pas une refonte du design. Le plan doit prévoir que le temps de correction est proportionnel au nombre de violations axe-core et au nombre de pages (4 pages × 2 locales = 8 URL dans `lighthouserc.json`).

## Files touched

- `frontend/playwright.config.ts` (ajout viewport / axe-core)
- `frontend/e2e/accessibility.spec.ts` (nouveau) ou extension d'un spec existant
- `frontend/e2e/responsive.spec.ts` (nouveau) ou même spec combiné
- `frontend/app/globals.css` (vérification, pas de modification — sauf si un contraste doit être corrigé)
- `frontend/components/*.tsx` (vérification des `alt`, `aria-`, `focus-visible` ; corrections ciblées si violations)
- `frontend/app/**/page.tsx` et clients (vérification, pas de refonte)
- `frontend/lighthouserc.json` (déjà présent — vérification, pas de modification sauf si un URL manque)
- `docs/research/s22-accessibilite-responsive.md` (déjà présent — pas de modification)
- `docs/plans/s22-accessibilite-responsive.md` (ce fichier)
- `docs/reviews/s22-accessibilite-responsive.md` (à créer en `/ks-review`)

## Test strategy

- **Unit** : pas de nouveaux composants → peu de tests unitaires. Vérifier que `Button`, `StreamingMessage`, `FileUpload` n'ont pas de régressions (tests existants : `StreamingMessage.test.tsx`, `FileUpload.test.tsx`, `Button` n'a pas de test unitaire dédié — vérifier via Playwright).
- **E2E (Playwright)** :
  - `axe-core` : 0 `critical`, 0 `serious` sur chaque page (fr et en).
  - Responsive : pas de scroll horizontal à 360px, 768px, 1280px sur chaque page.
  - Focus visible : chaque élément interactif a un focus visible après `Tab`.
  - `alt` : chaque `<img>` a `alt` (ou `alt=""` si décoratif).
  - Labels : chaque input a un `<label>` associé (vérifiable via axe-core).
- **Lighthouse (local)** : `npx lhci autorun` (ou `lighthouse` direct) sur chaque URL du `lighthouserc.json` ; score `accessibility` ≥ 0.9 (90).
- **Visuel** : vérification du responsive sur smartphone/tablette/desktop (via Playwright viewports ou navigateur réel si nécessaire).
- **Accessibilité** : `axe-core` couvre la plupart des AC. Pour le `keyboard navigation` (Tab logique), un test Playwright manuel (`keyboard.press('Tab')` + assertion sur `document.activeElement`) est nécessaire car axe-core ne vérifie pas l'ordre logique du Tab.

## Definition of Done

- Le diff du backend (`backend/`) est vide (interdit `progressive.py`, multi-tenant intact, pas de nouvelle logique backend).
- Le design-system (`docs/design-system.md`) n'a pas de nouveau composant/token inventé (vérifiable par `git diff docs/design-system.md` vide ou uniquement un commentaire sur le gap du test responsive).
- Le plan (`docs/plans/s22-accessibilite-responsive.md`) a `validated: yes`.
- Le `docs/research/s22-accessibilite-responsive.md` est présent et confirme l'absence de faux prémisses.
- Le `docs/designs/s22-accessibilite-responsive.md` et `.html` sont présents (référence statique).
- Les tests Playwright passent (`axe-core` 0 critical/serious, responsive sans scroll, focus visible, `alt`, labels).
- Le score Lighthouse (local) ≥ 90 sur chaque URL du `lighthouserc.json`.
- Le code ne casse pas le responsive existant (pas de scroll horizontal à 360px sur aucune page).
- La PR (`feature/s22-accessibilite-responsive`) porte uniquement le diff lié à s22 (tests, corrections ciblées, pas de refonte UI).
