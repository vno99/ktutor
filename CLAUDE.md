# CLAUDE.md

Ce fichier fournit des instructions complètes pour le développement de l'assistant de devoir IA multi-agents. Il sert de référence technique pour l'ensemble du projet.

---

## Vue d'ensemble du projet

Assistant de devoir intelligent utilisant une architecture multi-agents avec LangGraph. Le système permet aux élèves d'uploader des documents (cours, exercices, évaluations), de poser des questions via un chatbot, de générer des exercices personnalisés et de suivre leur progression. Les parents peuvent suivre les progrès de leurs enfants via un dashboard dédié.

### Objectifs principaux
- Fournir un assistant pédagogique personnalisé par matière
- **Correction progressive des exercices générés** : l'élève upload sa réponse, le système évalue et dévoile la correction par étapes si le score est insuffisant (seuil de < 80%)
- **Extraction automatique des scores** sur les copies d'évaluations corrigées par l'enseignant (via LLM multimodal)
- Suivre la progression des élèves avec des métriques claires
- Gamifier l'apprentissage via un système de récompenses

---

## Stack Technologique

### Frontend
- **Framework**: Next.js 16 (App Router)
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **API Client**: Axios
- **Langues**: TypeScript
- **i18n**: next-intl (français par défaut, anglais)
- **Accessibilité**: responsive smartphone (≥ 360px) + tablette (≥ 768px). WCAG 2.1 niveau A minimum.

### Backend API
- **Framework**: FastAPI (Python)
- **Authentification**: JWT RS256 avec RBAC (admin/parent/eleve)
- **Base de données**: PostgreSQL (utilisateurs, métadonnées, historique)
- **ORM**: SQLAlchemy + Alembic
- **File Storage**: S3 (SeaweedFS, S3-compatible)
- **Task Queue**: Celery + Redis

### IA et Agents
- **Orchestration**: LangGraph + langgraph-supervisor
- **Framework Agents**: LangChain
- **LLM (par défaut)**: Minimax-M3 (gratuit, suffisant pour le périmètre local actuel)
- **LLM alternatifs**: OpenAI GPT-4o / Mistral / Ollama (selon déploiement futur)
- **Vision LLM**: GPT-4o / Gemini (pour OCR manuscrit)
- **Vector Store**: ChromaDB (embeddings par matière)
- **Embeddings**: FastEmbed (ONNX) ou OpenAI

### Infrastructure
- **Conteneurisation**: Docker + docker-compose
- **Organisation**: Monorepo (frontend/backend/services)

---

## Architecture Système

### Vue d'ensemble
```
Frontend (Next.js 16)
    ↓
API Gateway (FastAPI)
    ↓
LangGraph Superviseur
    ↓
┌──────────────────────────────┐
│  Agents Spécialisés          │
│  ┌──────────┐ ┌──────────┐   │
│  │ Agent    │ │ Agent    │   │
│  │ Maths    │ │ Physique │   │
│  │ + RAG    │ │ + RAG    │   │
│  └──────────┘ └──────────┘   │
└──────────────────────────────┘
    ↓
ChromaDB (Vector Stores)
```

### Composants clés

#### 1. Superviseur (LangGraph)
- Route les requêtes vers l'agent compétent
- Gère les questions interdisciplinaires
- Synthétise les réponses multiples

#### 2. Agents spécialisés
- Un agent par matière (maths, physique, français, etc.)
- Chaque agent possède son propre RAG
- Prompt système spécifique à la matière

#### 3. Pipeline RAG
- Ingestion: PyMuPDF (PDF), python-docx (DOCX)
- OCR: pdfsmartocr (hybride) pour documents scannés
- Split: RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
- Embeddings: FastEmbed ou OpenAI
- Vector Store: ChromaDB (une collection par matière)

---

## Structure du Monorepo

```
assistant-devoir/
├── frontend/
│   ├── app/                    # Next.js App Router
│   │   ├── (auth)/             # Login, Register
│   │   ├── (dashboard)/        # Pages protégées
│   │   │   ├── admin/          # Admin dashboard
│   │   │   ├── parent/         # Parent dashboard
│   │   │   └── eleve/          # Student dashboard
│   ├── components/             # Composants UI réutilisables
│   ├── lib/                    # Zustand stores, Axios config
│   ├── types/                  # TypeScript types
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/                # FastAPI endpoints
│   │   │   ├── auth/           # Authentication routes
│   │   │   ├── users/          # User management
│   │   │   ├── documents/      # Document upload & management
│   │   │   ├── chat/           # Chatbot endpoints
│   │   │   ├── exercises/      # Exercise generation & submission
│   │   │   └── evaluations/    # Evaluation upload & scoring
│   │   ├── core/               # Core business logic
│   │   │   ├── auth/           # JWT, RBAC middleware
│   │   │   ├── database/       # SQLAlchemy models
│   │   │   └── config/         # Configuration
│   │   ├── services/           # Services
│   │   │   ├── rag/            # RAG pipeline
│   │   │   ├── agents/         # LangGraph agents
│   │   │   ├── ocr/            # OCR extraction
│   │   │   ├── correction/     # Correction progressive des exercices
│   │   │   └── rewards/        # Gamification system
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Conventions de Code

### Backend (Python)

```python
# Structure des endpoints FastAPI
@app.<method>("/<path>")
async def <endpoint_name>(
    # Parameters
    param: type = <default>,
    user: User = Depends(require_role(["role1", "role2"]))
) -> ResponseType:
    """
    Description de l'endpoint.
    
    Args:
        param (type): Description
        
    Returns:
        ResponseType: Description
    """
    # Logic
    return response
```

#### Nommage
- **Fichiers**: snake_case (ex: `user_service.py`)
- **Classes**: PascalCase (ex: `UserService`)
- **Fonctions/Méthodes**: snake_case (ex: `get_user_by_id`)
- **Variables**: snake_case (ex: `student_id`)
- **Endpoints**: kebab-case (ex: `/documents/upload`)

#### Types
- Toujours typer les fonctions avec `typing` ou `pydantic`
- Utiliser `Optional` pour les paramètres facultatifs

### Frontend (TypeScript)

```typescript
// Structure des composants Next.js
export default function ComponentName({ params }: { params: Type }) {
    // State
    const [state, setState] = useState<Type>(initial);
    
    // Effects
    useEffect(() => { ... }, [deps]);
    
    // Handlers
    const handleAction = async () => { ... };
    
    // Render
    return ( ... );
}
```

#### Nommage
- **Composants**: PascalCase (ex: `DashboardPage`)
- **Fichiers**: kebab-case (ex: `dashboard-page.tsx`)
- **Hooks**: camelCase avec `use` (ex: `useAuth`)
- **Stores**: camelCase (ex: `authStore`)
- **Types/Interfaces**: PascalCase (ex: `User`)

---

## APIs et Endpoints

### Authentification
```
POST /auth/login          → JWT access + refresh
POST /auth/refresh        → New access token
POST /auth/logout         → Token invalidation
GET  /auth/me             → Current user info
```

### Utilisateurs (Admin uniquement)
```
GET    /users             → List all users
POST   /users             → Create user
PUT    /users/{id}/role   → Update role
POST   /users/{parent_id}/children  → Link parent-child
GET    /users/{parent_id}/children  → List children
GET    /users/{id}        → User details
PUT    /users/{id}        → Update profile
```

### Documents
```
POST   /documents/upload   → Upload file (PDF/DOC/TXT/Image)
GET    /documents          → List documents (filter by subject, student)
GET    /documents/{id}     → Document details
PUT    /documents/{id}     → Update metadata
DELETE /documents/{id}     → Delete document
```

### Chatbot
```
POST   /chat/stream         → Streaming response (SSE)
GET    /chat/history        → Conversation history
GET    /chat/history/{id}   → Conversation details
```

### Exercices (Correction Progressive)

#### Génération
```
POST   /exercises/generate
Body: {
    subject: "maths",
    topic: "dérivées",
    difficulty: "facile" | "moyen" | "difficile",
    exercise_type: "qcm" | "probleme" | "flashcards" | "redaction"
}
Response: {
    exercise_id: string,
    statement: string,
    // La solution n'est PAS renvoyée immédiatement
    // Elle sera dévoilée progressivement lors de la correction
}
```

#### Soumission et Correction Progressive
```
POST   /exercises/submit
Body: multipart/form-data
    - exercise_id: string
    - answer: string (texte) OU image (upload)
Response: {
    exercise_id: string,
    score: float,                    // Score sur 20
    threshold_met: boolean,          // true si score >= 80%
    feedback: string,                // Commentaires sur la réponse
    correction_level: "none" | "partial" | "full",
    // Si score < 80%: correction_level = "partial" (indices seulement)
    // Si score >= 80%: correction_level = "full" (solution complète)
    correction_content: {
        // Niveau "partial" (score < 80%)
        hints: ["Indice 1", "Indice 2"],  // Indices pour guider
        next_steps: "Relisez le cours sur...",
        
        // Niveau "full" (score >= 80%)
        solution: string,            // Solution complète
        detailed_correction: string, // Correction étape par étape
        common_mistakes: string      // Erreurs fréquentes à éviter
    },
    attempt_number: number           // Numéro de tentative
}
```

#### Workflow de Correction Progressive
```
1. Élève génère un exercice (pas de solution visible)
2. Élève upload sa réponse (texte ou photo manuscrite)
3. Système évalue la réponse → calcule un score sur 20
4. Si score >= 80%:
   → Correction complète dévoilée (solution + explications)
   → Points bonus attribués
5. Si score < 80%:
   → Seulement des indices (correction partielle)
   → Élève peut retenter après avoir révisé
   → À chaque tentative, un peu plus de la correction est dévoilée
   → Après 3 tentatives infructueuses, correction complète dévoilée
```

#### États de Correction
| État | Score | Contenu dévoilé |
|------|-------|-----------------|
| `partial` | < 80% | Indices, conseils, points de révision |
| `partial_attempt_2` | < 80% | Indices plus précis, erreurs identifiées |
| `partial_attempt_3` | < 80% | Structure de la correction (sans solution) |
| `full` | >= 80% | Solution complète + explications |
| `full_after_attempts` | < 80% après 3 tentatives | Correction complète dévoilée |

### Évaluations
```
POST   /evaluations/upload/enonce        → Upload exam statement (optional)
POST   /evaluations/upload/copie-corrigee → Upload corrected exam
GET    /evaluations                      → List evaluations
GET    /evaluations/{id}                 → Evaluation details
POST   /evaluations/{id}/score-manual    → Manual score entry (admin/parent)
POST   /evaluations/{id}/reprocess       → Reprocess via LLM (admin)
```

---

## Permissions RBAC

| Endpoint | Admin | Parent | Élève |
|----------|-------|--------|-------|
| `/auth/*` | ✅ | ✅ | ✅ |
| `/users/*` | ✅ (admin only) | ❌ | ❌ |
| `/users/children` | ✅ | ✅ (ses enfants) | ❌ |
| `/documents/upload` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |
| `/documents/*` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |
| `/chat/stream` | ✅ | ✅ (ses enfants) | ✅ (soi) |
| `/chat/history` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |
| `/exercises/generate` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |
| `/exercises/submit` | ✅ | ❌ (lecture seule) | ✅ (soi) |
| `/exercises/history` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |
| `/evaluations/*` | ✅ (tous) | ✅ (ses enfants) | ✅ (soi) |

---

## Workflows Clés

### 1. Upload de document

```
1. Élève upload un fichier (PDF/DOC/Image)
2. Déclenchement d'une tâche Celery:
   a. OCR (si image ou PDF scanné)
   b. Chunking (RecursiveCharacterTextSplitter)
   c. Vectorisation (FastEmbed/OpenAI)
   d. Stockage dans ChromaDB
3. Mise à jour du statut ("indexed" / "error")
4. Attribution de points (10 points pour upload)
```

### 2. Génération et correction progressive d'exercice

```
1. Élève demande un exercice
2. LLM génère l'énoncé + solution (stockée)
3. L'élève répond (texte ou photo manuscrite)
4. Si photo: LLM multimodal transcrit l'écriture
5. Évaluation automatique de la réponse (selon le type d'exercice):
   a. QCM: tout ou rien (toutes bonnes réponses = réussite, sinon échec)
   b. Rédaction / Problème: appréciation qualitative du LLM (positive = réussite, sinon échec)
6. Décision de dévoilement:
   a. Si réussite: correction complète + points bonus
   b. Si échec: indices uniquement + points de participation
   c. Après 3 tentatives: correction complète dévoilée
7. Enregistrement de l'historique des tentatives
8. Attribution des points (5 points de base + bonus)
```

### 3. Traitement d'une évaluation corrigée

```
1. Élève upload sa copie corrigée (PDF/Image)
2. Tâche Celery:
   a. Vision LLM analyse le document
   b. Extraction du score (regex + LLM)
   c. Extraction des annotations et commentaires
   d. Stockage structuré
3. Score disponible dans le dashboard
4. Attribution de points (10 points pour upload copie)
```

---

## Correction Progressive des Exercices (Détail)

### Algorithme de correction

```python
class ProgressiveCorrection:
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        # Pas de seuil numérique : la "réussite" dépend du type d'exercice
        # - QCM : toutes les bonnes réponses cochées
        # - Rédaction : appréciation LLM positive

    async def evaluate(self, exercise_id: str, answer: str, user_id: str) -> CorrectionResult:
        # 1. Récupérer l'exercice et sa solution
        exercise = await get_exercise(exercise_id)

        # 2. Évaluer la réponse selon le type d'exercice
        #    - QCM : binaire (is_success = toutes bonnes réponses)
        #    - Rédaction : is_success = (LLM feedback == "positive")
        is_success, feedback = await self._grade_answer(
            answer=answer,
            exercise=exercise
        )

        # 3. Récupérer l'historique des tentatives
        attempts = await get_attempts(exercise_id, user_id)
        attempt_number = len(attempts) + 1

        # 4. Déterminer le niveau de correction à dévoiler
        if is_success:
            # Réussite → correction complète
            correction_level = "full"
            correction_content = {
                "solution": exercise.solution,
                "detailed_correction": exercise.detailed_solution,
                "common_mistakes": exercise.common_mistakes
            }
            bonus_points = 2
        elif attempt_number >= self.max_attempts:
            # Trop de tentatives → correction complète
            correction_level = "full_after_attempts"
            correction_content = {
                "solution": exercise.solution,
                "detailed_correction": exercise.detailed_solution,
                "message": "Après plusieurs tentatives, voici la correction complète."
            }
            bonus_points = 0
        else:
            # Correction partielle → indices
            correction_level = "partial"
            correction_content = self._generate_hints(
                exercise=exercise,
                attempt=attempt_number,
                answer=answer
            )
            bonus_points = 0

        # 5. Enregistrer la tentative
        await save_attempt(exercise_id, user_id, answer, is_success, correction_level)

        # 6. Attribuer les points
        points = 5  # Points de base pour participation
        if bonus_points:
            points += bonus_points
        await reward_service.award_points(user_id, "exercise_submit", points)

        return CorrectionResult(
            is_success=is_success,
            feedback=feedback,
            correction_level=correction_level,
            correction_content=correction_content,
            attempt_number=attempt_number
        )

    async def _grade_answer(self, answer: str, exercise: Exercise) -> tuple[bool, str]:
        """Évalue la réponse selon le type d'exercice.

        Returns:
            (is_success, feedback)
        """
        if exercise.type == "qcm":
            # QCM : tout ou rien
            correct_answers = set(exercise.correct_options)
            user_answers = set(answer.selected_options)
            is_success = (correct_answers == user_answers)
            feedback = "Bonne réponse !" if is_success else "Réponse incorrecte."
            return is_success, feedback
        else:
            # Rédaction / Problème : appréciation LLM
            return await self._grade_with_llm(answer=answer, exercise=exercise)

    async def _grade_with_llm(self, answer: str, exercise: Exercise) -> tuple[bool, str]:
        """Évalue une réponse libre via LLM (appréciation qualitative)."""
        prompt = f"""Tu es un enseignant. Évalue la réponse de l'élève.

Énoncé : {exercise.statement}
Réponse attendue : {exercise.solution}
Réponse de l'élève : {answer}

Donne ton appréciation en une phrase, puis conclus par :
- "VERDICT: REUSSITE" si la réponse est correcte ou très proche
- "VERDICT: ECHEC" sinon"""
        result = await llm.invoke(prompt)
        is_success = "VERDICT: REUSSITE" in result.upper()
        return is_success, result

    def _generate_hints(self, exercise: Exercise, attempt: int, answer: str) -> dict:
        """Génère des indices progressifs en fonction de la tentative."""
        hints = []
        if attempt == 1:
            hints = ["Relisez la définition du concept clé.", "Vérifiez vos calculs étape par étape."]
        elif attempt == 2:
            hints = ["L'erreur se situe au niveau de...", "Appliquez cette formule..."]

        return {
            "hints": hints,
            "next_steps": "Révisez le cours sur...",
            "attempt": attempt,
            "remaining_attempts": self.max_attempts - attempt
        }
```

---

## Multi-Tenancy (Isolation des Données)

Chaque élève ne doit voir que **ses** documents, **ses** exercices, **ses** évaluations. L'isolation se fait d'abord par élève, puis par matière.

### Règles d'isolation
- **PostgreSQL** : toutes les tables métier ont une colonne `student_id` (FK). Toutes les requêtes filtrent par `student_id` (et vérifient qu'il correspond au `student_pseudo` du JWT).
- **ChromaDB** : convention de nommage `rag_<subject>_<student_pseudo>` (ex: `rag_maths_ali_baba`). Le RAG ne lit que la collection de l'élève courant.
- **SeaweedFS (S3)** : préfixe de clé `students/<student_pseudo>/<document_id>`. Le SDK Python `minio>=7.2` est utilisé (compatible S3).
- **JWT** : le `student_pseudo` est inclus dans le token, propagé partout.

### Contrôle
- **Middleware FastAPI** : vérifie que `student_id` de l'URL/body correspond au `student_pseudo` du JWT (ou à un enfant du parent authentifié).
- **Tests** : pour chaque endpoint, au moins un test vérifie qu'un élève A ne peut pas lire les données d'un élève B (test d'isolation cross-tenant).

## Identité & Données Personnelles

> ⚠️ Le projet est en **local** pour l'instant. Pas de conformité RGPD/CNIL gérée.
> **Aucune donnée personnelle réelle** (nom, prénom, email). Les utilisateurs sont identifiés par un **pseudo** uniquement.
> Si déploiement futur : ajouter consentement parental, droit à l'effacement, hébergement UE, anonymisation.

## Internationalisation (i18n)

- **Framework** : `next-intl` (App Router compatible)
- **Langues supportées** : français (par défaut), anglais
- **Emplacement** : `frontend/messages/<locale>.json`
- **Backend** : les réponses API exposent les textes dans la langue demandée via header `Accept-Language` (préparé, à implémenter plus tard).

## Accessibilité

- **Responsive** : smartphone (≥ 360px) et tablette (≥ 768px) prioritaires. Desktop secondaire.
- **Standards** : WCAG 2.1 niveau A minimum (contrastes, navigation clavier, focus visible).
- **Tests** : Lighthouse Accessibility ≥ 90 sur les pages principales.

## Observabilité

- **Logs structurés** : `loguru` côté Python, `pino` côté TypeScript. Format JSON.
- **Tracing** : OpenTelemetry sur FastAPI + Celery. Export vers console en local (vers Jaeger/Tempo plus tard).
- **Métriques** : Prometheus côté backend (compteurs : requêtes par endpoint, latence, taille des uploads, succès/échecs d'OCR, score moyen des exercices). Endpoint `/metrics`.
- **Alerting** : règles minimales (taux d'erreur > 5%, latence p95 > 5s, Celery queue > 100 tâches) — affichage local via Grafana ou simple log en console pour l'instant.
- **Tracing LLM** : logs de chaque appel LLM (prompt, completion, durée, tokens si disponibles) via un wrapper LangChain.

## Variables d'Environnement

```bash
# .env.example

# API
API_PORT=8000
API_HOST=0.0.0.0
DEBUG=true

# Auth
JWT_SECRET_KEY=<your-secret>
JWT_REFRESH_SECRET_KEY=<your-refresh-secret>
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/assistant
DATABASE_POOL_SIZE=20

# LLM
LLM_PROVIDER=minimax  # valeurs: minimax | openai | ollama
MINIMAX_API_KEY=<not-required-yet>
MINIMAX_MODEL=minimax-m3
OPENAI_API_KEY=<optional>
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDINGS_MODEL=text-embedding-3-small
OLLAMA_BASE_URL=http://ollama:11434  # Optional

# Observabilité
OTEL_EXPORTER=console  # console | otlp
LOG_LEVEL=INFO
METRICS_ENABLED=true

# Vector Store
CHROMA_PERSIST_DIRECTORY=./chroma_data
VECTOR_STORE_COLLECTION_PREFIX=rag_

# File Storage
S3_ENDPOINT=localhost:8333
S3_ACCESS_KEY=<your-key>
S3_SECRET_KEY=<your-secret>
S3_BUCKET=assistant-documents

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WEBSOCKET_URL=ws://localhost:8000/ws

# Correction
MAX_CORRECTION_ATTEMPTS=3       # Nombre max de tentatives avant correction complète
```

---

## Développement

### Installation

```bash
# 1. Cloner le repo
git clone <repository-url>
cd assistant-devoir

# 2. Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend
cd ../frontend
npm install

# 4. Services (Docker)
docker-compose up -d postgres redis seaweedfs chroma

# 5. Démarrer
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: Celery
cd backend && celery -A app.services.tasks worker --loglevel=info

# Terminal 3: Frontend
cd frontend && npm run dev
```

### Tests

```bash
# Backend
pytest backend/tests

# Frontend
npm test
```

---

## Déploiement

### Docker Compose (Development)
```bash
docker-compose up -d
```

### Production
```bash
# Build images
docker build -t assistant-devoir-frontend frontend/
docker build -t assistant-devoir-backend backend/

# Deploy (exemple avec Azure/AWS)
docker push <registry>/assistant-devoir-frontend
docker push <registry>/assistant-devoir-backend
# ... deploy via Kubernetes or Azure Container Apps
```

---

## Plan de Développement

> ⚠️ Calendrier purement informatif. Le projet est en local, sans contrainte de délais.

### Phase 1: POC
- [ ] Pipeline RAG simple (PDF → Chunks → ChromaDB)
- [ ] Agent unique (Maths) avec LangChain
- [ ] Test LLM multimodal sur écriture manuscrite
- [ ] Script Python fonctionnel

### Phase 2: MVP
- [ ] API FastAPI endpoints: `/chat`, `/documents/upload`
- [ ] Frontend minimal: chat + upload
- [ ] Deux agents (Maths + Physique) avec superviseur
- [ ] Streaming des réponses (SSE)

### Phase 3: Rôles et Sécurité
- [ ] Authentification JWT
- [ ] PostgreSQL avec modèles Users/Roles
- [ ] Middleware RBAC
- [ ] Isolation des documents par élève
- [ ] Dashboard parent simple

### Phase 4: Pédagogie
- [ ] Génération d'exercices (QCM, problèmes, flashcards)
- [ ] **Correction progressive** : soumission d'exercices avec dévoilement progressif de la correction
- [ ] Évaluations: upload copie corrigée + extraction score
- [ ] Dashboards élève/parent avec progression

### Phase 5: Finalisation
- [ ] Système de récompenses (points, historique)
- [ ] Notifications
- [ ] UI/UX finale
- [ ] Tests et documentation
- [ ] Déploiement

---

## Ressources et Références

### Documentation technique
- [LangChain Documentation](https://python.langchain.com/docs)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)

### Projets inspirants
- UsiEdu: Système multi-agents éducatif
- AutoGen: Framework Microsoft pour agents
- Tutor-multi-ai-agent: Assistant pédagogique sur GitHub
- Ethel ETH Zurich: RAG pour cours universitaires

---

## Notes importantes

### Workflow de correction progressive
- **Ne pas dévoiler la correction complète** en cas d'échec (sauf après 3 tentatives)
- **QCM** : tout ou rien (toutes bonnes réponses = réussite, sinon échec)
- **Rédaction / Problème** : appréciation qualitative du LLM (réussite = appréciation positive)
- **Transmettre l'image manuscrite au LLM multimodal** pour transcription
- **Historique des tentatives** conservé pour suivi pédagogique

### Sécurité
- Les JWT doivent être signés avec RS256 (pas HS256)
- Les mots de passe sont hashés avec bcrypt
- Tous les endpoints API doivent être protégés par RBAC
- **Multi-tenancy** : isolation stricte par élève (puis par matière) dans ChromaDB et PostgreSQL. Voir section dédiée.
- Fichiers uploadés : scan anti-malwares prévu en phase production uniquement

### Performance
- Utiliser le streaming (SSE) pour les réponses du chatbot
- Mettre en cache les embeddings fréquemment utilisés
- Utiliser des tâches asynchrones (Celery) pour l'OCR et l'indexation
- Limiter la taille des fichiers uploadés à 20MB

### Coûts
- Non applicable pour l'instant — projet local, LLM gratuit (Minimax-M3).
- Pas de mise en cache des embeddings, pas d'optimisation de coûts.

---

*Ce fichier sera mis à jour au fur et à mesure du développement. Toute décision architecturale majeure doit être documentée ici.*
@AGENTS.md
