# Guide — Élève / Student Guide

## Français

### Créer un compte <a id="creer-compte"></a>
Créez votre compte via `/auth/login` ou `/auth/register`. Utilisez un pseudo (pas de données personnelles réelles). Une fois connecté, votre `pseudo` est stocké dans le JWT.

### Uploader un document <a id="upload-document"></a>
Depuis le tableau de bord élève (`/dashboard/eleve`), utilisez le bouton d'upload pour envoyer un cours (PDF, DOCX, image). Le fichier est indexé dans ChromaDB via la tâche Celery (OCR + chunking).

### Dialoguer avec le chatbot <a id="chat"></a>
Accédez au chat (`/chat`) pour poser des questions sur vos cours. Le super-agent LangGraph route vers l'agent compétent (maths, physique, français) et répond en streaming (SSE).

### Générer un exercice <a id="generer-exercice"></a>
Depuis le dashboard ou le chat, demandez la génération d'un exercice (`/exercises/generate`). Choisissez la matière, le sujet, la difficulté et le type (QCM, problème, flashcards, rédaction).

### Soumettre une réponse <a id="repondre"></a>
Téléchargez votre réponse (texte ou photo manuscrite) via `/exercises/submit`. Le système évalue automatiquement : si le score est ≥ 80 %, la correction complète est dévoilée ; sinon, seuls des indices sont donnés. Après 3 tentatives, la correction complète est dévoilée.

### Voir le tableau de bord <a id="dashboard"></a>
Le tableau de bord élève (`/dashboard/eleve`) affiche vos métriques de progression : points, historique des exercices, évaluations et récompenses attribuées.

---

## English

### Create an account <a id="creer-compte-en"></a>
Sign up or log in at `/auth/login` or `/auth/register`. Use a pseudo (no real personal data). Once logged in, your `pseudo` is stored in the JWT.

### Upload a document <a id="upload-document-en"></a>
From the student dashboard (`/dashboard/eleve`), use the upload button to submit a course (PDF, DOCX, image). The file is indexed in ChromaDB via a Celery task (OCR + chunking).

### Chat with the assistant <a id="chat-en"></a>
Access the chat (`/chat`) to ask questions about your courses. The LangGraph supervisor routes to the relevant agent (maths, physics, French) and responds via streaming (SSE).

### Generate an exercise <a id="generer-exercice-en"></a>
From the dashboard or chat, request an exercise (`/exercises/generate`). Select subject, topic, difficulty, and type (QCM, problem, flashcards, essay).

### Submit an answer <a id="repondre-en"></a>
Upload your answer (text or handwritten photo) via `/exercises/submit`. The system grades automatically: if score ≥ 80%, full correction is revealed; otherwise, only hints. After 3 attempts, full correction is revealed.

### View the dashboard <a id="dashboard-en"></a>
The student dashboard (`/dashboard/eleve`) shows your progress metrics: points, exercise history, evaluations, and awarded rewards.
