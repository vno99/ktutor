# ADR 002 — Réécrire le POC Python from scratch

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le repo contient un POC Python fonctionnel :

- `src/main.py` — CLI interactif avec menu textuel (5 options)
- `src/agents/math_agent.py` — Agent LangChain ReAct avec un outil RAG et un outil calculatrice
- `src/ingestion/document_loader.py` — PyMuPDFLoader + RecursiveCharacterTextSplitter
- `src/rag/vector_store.py` — ChromaDB + OpenAIEmbeddings
- `src/ocr/multimodal_ocr.py` — GPT-4o Vision + fallback Tesseract
- `src/ocr/deepseek_ocr.py` — Client DeepSeek-OCR singleton
- `requirements.txt` — langchain 0.3, langchain-openai, langgraph, chromadb, pymupdf, fastapi
- `test_quick.py` — script de validation

Le PRD demande une architecture cible très différente : multi-agents supervisé par LangGraph, FastAPI avec JWT RS256, frontend Next.js 16, multi-tenant strict par élève, PostgreSQL pour les users, Celery pour les tâches lourdes, MinIO pour les fichiers, RBAC admin/parent/élève, observabilité (logs structurés, OTel, Prometheus).

Question : peut-on faire évoluer le POC vers la cible, ou faut-il réécrire ?

## Decision

**Réécrire from scratch** (décision utilisateur, 2026-08-28). Le code POC est conservé temporairement dans le repo pour mémoire (jusqu'à ce que le pipeline nettoie), mais tout nouveau code va dans `backend/app/` et `frontend/app/` selon la nouvelle structure.

Les **patterns** du POC qui survivent à la réécriture :

- Le découpage `ingestion / rag / agents / ocr` (les couches existent toujours, elles sont juste déplacées sous `backend/app/services/`).
- L'usage de `langchain.text_splitter.RecursiveCharacterTextSplitter` avec `chunk_size=1000, chunk_overlap=200` (convention documentée dans `CLAUDE.md`).
- L'usage de `chromadb.PersistentClient` avec un répertoire de persistance venant d'env.
- L'isolation ChromaDB par collection nommée `rag_<subject>_<pseudo>` (multi-tenant).

Les **patterns du POC qui ne survivent pas** :

- L'agent ReAct unique → remplacé par un superviseur LangGraph avec agents spécialisés par matière (s05).
- Le CLI interactif → remplacé par des endpoints FastAPI (s09) et un frontend Next.js (s11).
- Le singleton `DeepSeekOCR` → remplacé par un client HTTP vers un service OCR séparé (s01 agentic notes).
- `OpenAIEmbeddings` par défaut → remplacé par FastEmbed (ONNX) ou OpenAI selon `LLM_PROVIDER` (CLAUDE.md).
- Pas de base de données métier dans le POC → PostgreSQL + SQLAlchemy + Alembic à créer.

## Considered options

- **Faire évoluer le POC (refactor incrémental)** — rejeté par l'utilisateur. Le saut architectural (multi-tenant, JWT, RBAC, API, frontend) est trop grand : chaque PR de refactor toucherait à tout. Risque de régressions silencieuses et de dette technique qui s'accumule. Pour un POC de validation, ça passait ; pour un produit local structuré, on réécrit.

- **Garder le POC en mode « script d'expérimentation » à côté du produit** — rejeté. Deux bases de code Python différentes pour le même domaine est un anti-pattern. Les concepts divergeraient.

- **Réécrire from scratch (choix retenu)** — permet d'imposer les conventions du PRD dès le premier commit, sans traîner les hypothèses du POC.

## Consequences

- **Court terme** : on perd l'élan du POC (il marchait sur Mistral + OpenAI embeddings). Acceptable parce que le POC était mono-utilisateur, sans auth, sans API, sans frontend — il n'aurait pas survécu à la première story d'auth (s12).
- **Moyen terme** : le pattern superviseur LangGraph + agents spécialisés est plus expressif mais demande un investissement initial (définir le state schema, les nodes, les edges). Le PRD le mandate explicitement.
- **Hygiène** : nettoyer les fichiers POC (`src/`, `test_quick.py`, `requirements.txt`) à la fin de l'ADR ou dans une story dédiée de ménage. Pour l'instant, on les laisse pour mémoire et pour comparer.
- **Pas de migration de données** : le POC n'avait pas de BDD persistante, donc rien à migrer. ChromaDB est supprimé et recréé.
