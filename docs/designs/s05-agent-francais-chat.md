---
name: design-s05-agent-francais-chat
description: s05-agent-francais-chat — la story est purement backend, aucun écran à concevoir. Référence vers s11 pour l'écran /chat qui consommera l'API.
metadata:
  type: project
  story: s05-agent-francais-chat
---

# Design — Story s05-agent-francais-chat

> **Aucun écran à produire.** Cette story est purement backend (agent LangChain + superviseur typé + collection ChromaDB dédiée). Tous les acceptance criteria portent sur la CLI, la couche de service, ou les tests d'isolation multi-tenant. Aucun composant du design system n'est consommé.

## Rappel de la story

**As an** élève **I want** poser une question sur un cours de français **so that** j'obtiens une réponse qui s'appuie sur mes documents de français.

**Complexity** : 3 — Second agent + superviseur + collection ChromaDB séparée.

### Acceptance criteria (résumé)

| AC | Surface | Type |
| --- | --- | --- |
| AC1 | CLI : `--subject francais` | **CLI flag** (typer) |
| AC2 | Collection `rag_francais_<pseudo>` | **Backend service** |
| AC3 | Superviseur LangGraph / dispatcher typé | **Backend service** |
| AC4 | Réponse cite des sources | **Sortie texte structurée** |
| AC5 | Test « no document » en français | **Test** |
| AC6 | Test cross-tenant `pseudo_a`/`pseudo_b` | **Test** |

**Aucune surface UI/Web.** La commande `chat` reste un point d'entrée CLI (cf. `backend/app/cli.py:297-323`).

## Pourquoi pas de design

Règle du contrat ks-design (lignes du skill) :

> **Vous êtes INTERDIT de** :
> - Produire un design sans design system existant.
> - Inventer un composant, token, couleur ou espacement en dehors du design system.
> - Concevoir un écran que la story ne demande pas.

Cette story ne demande aucun écran. Produire un mockup HTML ici violerait la troisième interdiction.

## Écrans futurs qui consommeront l'API s05

L'API/langchain de s05 sera consommée visuellement par les stories UI suivantes, **pas avant** :

| Écran | Story | Composants DS consommés |
| --- | --- | --- |
| `/chat` (page principale) | **s11-frontend-upload-chat** | `<StreamingMessage>` avec `aria-live="polite"`, `<Card>`, `<Select>` pour la matière, `<Button>`, `<LanguageSwitcher>` |
| Historique des conversations | **s19-historique-conversations** | `<Table>`, `<Card>`, `<Avatar>` |
| Dashboard parent (vue enfant) | **s17-dashboard-parent** | `<Tabs>` (matières), `<Card>` (résumé chat) |
| Notifications | **s25-notifications-in-app** | `<NotificationBell>`, `<Toast>` |

**Aucun de ces écrans n'est dans le périmètre de s05.** Ils seront conçus au moment de leur story respective via `/ks-design s11`, `/ks-design s19`, etc., qui liront **ce document** pour comprendre le contrat de sortie du superviseur (sélection par `--subject`, format `ChatResult.answer` + `ChatResult.sources`).

## Contrat visuel à fixer pour les stories en aval

Bien que s05 ne produise pas d'écran, le contrat de sortie de l'agent est **imposé** aux futures stories UI. Documenter ici pour qu'elles le respectent sans réinventer.

### Format de la réponse texte (CLI → future UI)

```typescript
type ChatResult = {
  answer: string;        // réponse en français, citations incluses au format [source: <filename>, chunk <n>]
  sources: Array<{
    filename: string;    // ex: "lecon_francais.pdf"
    chunk_index: number; // 0-based, integer
  }>;
};
```

### Comportement UI attendu (à implémenter en s11)

- **Streaming** : la réponse `answer` arrive par chunks SSE (s09 + s11). Le composant `<StreamingMessage>` accumule les tokens.
- **Citations** : à chaque citation `[source: ...]` détectée dans le texte, afficher un badge inline (couleur `--color-text-secondary` ou `--color-info` si la story design le décide) avec tooltip au hover.
- **Multi-matière** : le sélecteur `<Select>` de matière (maths / français) contrôle l'argument `subject` envoyé à l'API. La liste des matières vient de `Subject` enum (backend).
- **État vide** (AC5) : quand l'agent retourne `chat_no_document_message` (« Je n'ai pas trouvé d'information sur ce sujet dans tes documents »), afficher ce message dans une `<Card>` centrée, en `text-text-secondary`, sans icône d'erreur.
- **État d'erreur** (réseau, LLM timeout) : `<Toast>` rouge 4s en haut (rôle `status`), bouton « Réessayer » qui re-tente la même requête.
- **État de chargement** : 3 points animés (`prefers-reduced-motion` respecté) + `aria-busy="true"` sur la zone de réponse.
- **Multi-tenant** : côté UI, le `pseudo` vient du JWT (s12) — la UI ne le demande jamais à l'utilisateur.

Ces comportements seront **re-validés en s11** quand l'écran sera conçu et implémenté. Le design system § « UI patterns imposés » (loading / empty / error / success, lignes 203-210) s'applique.

## Composants du design system référencés (pour info, pas à utiliser ici)

| Composant | Rôle pour les stories en aval |
| --- | --- |
| `<Select>` (natif) | Sélecteur de matière (maths / français) dans l'écran `/chat` |
| `<StreamingMessage>` (avec `aria-live="polite"`) | Affichage incrémental des chunks SSE |
| `<Card>` (header / body / footer) | Conteneur pour le message de l'agent |
| `<Button>` (primary) | Bouton « Poser la question » |
| `<LanguageSwitcher>` | FR/EN (s11 + s21) |
| `<Toast>` | Notifications d'erreur (s25) |

## Gaps du design system pour cette story

**Aucun.** La story ne consomme pas le design system.

## Mockup

**Aucun mockup HTML.** Justification : la story n'a pas d'écran. Le `docs/designs/s05-agent-francais-chat.html` n'est pas créé — sa création serait une violation du contrat ks-design.

Pour les stories futures qui consommeront l'agent s05, le mockup sera produit dans :

- `docs/designs/s11-frontend-upload-chat.html` (écran /chat)
- `docs/designs/s19-historique-conversations.html` (historique)
- `docs/designs/s17-dashboard-parent.html` (vue parent)

## Liens

- `docs/stories.md:155-186` — story s05 complète.
- `docs/research/s05-agent-francais-chat.md` — recherche (362 lignes, déjà livrée).
- `docs/design-system.md` — design system (catalogue composants, tokens).
- `docs/architecture.md` § Frontend — cadre général.
- ADR 003 (langgraph-supervisor) — non applicable en l'état (s05 = dispatcher typé simple, pas de `StateGraph`).
- ADR 004 (rag-isolation-by-collection) — convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 006 (frontend-nextjs-app-router) — cadre i18n + a11y pour les futures stories UI.

## Pré-requis pour passer à `/ks-plan`

Aucun gap visuel à trancher. Le plan s05 peut être écrit sans design additionnel. Les 3 décisions ouvertes (D1 forme du superviseur, D2 location des types partagés, D3 validation sujet côté CLI+agent) sont tranchées dans la recherche s05 (sections « Décisions d'architecture »).
