# ADR 003 — Orchestration LangGraph + langgraph-supervisor

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le PRD liste deux matières (Maths + Français) avec un agent spécialisé par matière, et la possibilité de questions interdisciplinaires. Le POC a un agent LangChain ReAct unique qui ne scale pas vers ce besoin (pas de routing, pas de synthèse multi-agents).

Question : comment orchestrer plusieurs agents spécialisés ?

## Decision

Adopter **LangGraph** comme framework d'orchestration, avec le pattern **supervisor** (via `langgraph-supervisor`).

- Chaque matière a son propre agent (noeud LangGraph) avec son RAG dédié (`rag_<subject>_<pseudo>`).
- Un superviseur (noeud LangGraph racine) reçoit la question, choisit l'agent (ou les agents, en cas de question interdisciplinaire), et synthétise les réponses.
- Le state du graphe est typé (`TypedDict`) et propagé entre les noeuds.
- Le streaming est natif via `astream_events` (compatible SSE FastAPI).
- Le LLM par défaut est **Minimax-M3** (gratuit, local, suffisant pour le POC). Le provider est commutable via `LLM_PROVIDER` (minimax | openai | ollama | mistral).

Pour le POC, le routage est explicite par matière (le client envoie `--subject maths` ou `/subject=francais`). Le routage par contenu est une itération future (s05 trap).

## Update — s05

La story s05-agent-francais-chat livre un **dispatcher Python typé**
(`SubjectSupervisor` dans `backend/app/services/agents/supervisor.py`)
plutôt qu'un `StateGraph` `langgraph`. Justifications : (1) le routage
par flag est un `if` typé, (2) `langgraph-supervisor` n'est pas encore
installé (cf. `docs/research/s05-agent-francais-chat.md` § D1), (3) la
migration vers un `StateGraph` est mécanique et reste encapsulée dans
`SubjectSupervisor` — les agents individuels ne changent pas.

Le `StateGraph` arrive quand le routage par contenu est implémenté (le
client enverra une question, et le superviseur classifie la matière au
lieu de la recevoir du caller).

## Considered options

- **Multi-agent pur sans superviseur (chaque agent est appelé en parallèle, résultats fusionnés par un post-traitement)** — rejeté parce que la fusion est fragile (qui décide du bon agent ? qui tranche en cas de désaccord ?) et ne scale pas vers N matières.

- **Routeur LLM unique (un seul LLM classifie la matière, puis appelle l'agent)** — plus simple que le superviseur, mais ne gère pas les questions interdisciplinaires (« explique-moi la poésie des maths »). Le superviseur est plus expressif.

- **Un seul agent avec des outils par matière (RAG maths + RAG français)** — c'est l'approche du POC. Rejeté parce que la séparation par agent permet des prompts plus ciblés (un agent maths n'a pas besoin de la consigne « tu ne réponds qu'en français littéraire »).

- **LangGraph + langgraph-supervisor (choix retenu)** — donne le superviseur + le streaming + le state typé. Aligné sur le PRD.

## Consequences

- **Expressivité** : le superviseur peut chaîner des agents (maths puis français), ou en appeler deux en parallèle et fusionner. Le state typé documente le contrat.
- **Coût d'observabilité** : tracer un graphe LangGraph demande de comprendre le state et les edges. L'observabilité (s23) doit wrapper LangChain callbacks pour émettre un log par transition de noeud.
- **Tests** : tester un graphe LangGraph est plus lourd que tester un agent unique (le state peut être complexe). On utilise `langgraph.pregel.Pregel` directement pour les tests unitaires du graphe, sans le runtime complet.
- **Pas de dépendance à un service externe d'orchration** (pas de Temporal, pas de Prefect) — LangGraph gère la persistance du state via checkpointer (en mémoire pour le POC, Redis plus tard).
