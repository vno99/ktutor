# PRD — ktutor

> Généré par `/ks-init` le 2026-08-27. Source de vérité technique : `CLAUDE.md`.

## Vision

ktutor est un assistant pédagogique intelligent pour **collégiens**, basé sur une architecture multi-agents (LangGraph). L'élève uploade ses cours et exercices (PDF, images dactylographiées ou manuscrites), pose des questions, génère des exercices personnalisés, et progresse à son rythme. Le système évalue ses réponses, **dévoile la correction de manière progressive** (seulement des indices d'abord, puis la solution complète), et suit la progression dans le temps. Les parents peuvent suivre les progrès de leurs enfants depuis un dashboard dédié.

La différenciation produit tient en deux mécanismes : (1) la **correction progressive** qui force l'élève à chercher avant d'avoir la solution, et (2) l'**extraction automatique de scores** sur les copies d'évaluations corrigées par l'enseignant via LLM multimodal.

## Personas

- **Élève (collège)** : utilisateur principal. Pose des questions sur ses cours, génère des exercices, upload ses réponses (texte ou photo manuscrite), reçoit une correction progressive. Niveau 6e-3e. Une ou plusieurs matières selon le niveau (maths, français dans le périmètre initial).
- **Parent** : suit passivement la progression de son enfant (scores, temps passé, matières actives). Lecture seule. Voit les dashboards de progression.
- **Admin** : gère les utilisateurs, configure les matières, accède à tous les comptes. Opérationnel uniquement (pas d'usage pédagogique direct).

## Problème

Les collégiens manquent d'un accompagnement pédagogique **personnalisé** entre les cours. Les parents n'ont pas de visibilité fine sur la progression réelle de leur enfant (au-delà des bulletins scolaires). Les outils existants (cahiers de vacances, apps généralistes) ne s'adaptent ni au programme ni au niveau réel de l'élève, et ne proposent pas de mécanisme de **correction qui force la réflexion**.

## Objectifs produit

1. **Réduction du temps d'attente pédagogique** : un élève qui pose une question sur son cours reçoit une réponse sourcée en moins de 10 secondes (P95).
2. **Engagement via la correction progressive** : au moins 60% des élèves qui échouent à un exercice retentent au moins une fois (mesure de l'effet "gamification" du mécanisme).
3. **Visibilité parent** : 100% des parents liés à un compte enfant peuvent accéder aux dashboards de progression en lecture seule.
4. **Couverture multi-matière** : le système supporte au minimum Maths (POC) et Français (phase 2), chacun avec son propre RAG et son agent spécialisé.
5. **Extraction automatique de scores** : 90% des copies d'évaluation uploadées produisent un score exploitable sans saisie manuelle.

## Périmètre (in)

- **Upload de documents** : PDF, images dactylographiées, images manuscrites (OCR via LLM multimodal).
- **Pipeline RAG par matière** : ingestion → chunking → embeddings → ChromaDB. Une collection par (matière × élève).
- **Chat RAG** : l'élève pose des questions en langage naturel, l'agent spécialisé de la matière répond en s'appuyant sur les documents uploadés.
- **Génération d'exercices** : QCM (tout-ou-rien), problème (appréciation LLM), rédaction (appréciation LLM), flashcards.
- **Correction progressive** : seuils basés sur le type d'exercice (QCM : toutes bonnes réponses, rédaction : appréciation positive). 3 tentatives max avant correction complète.
- **Évaluations** : upload d'une copie corrigée par l'enseignant → extraction automatique du score + annotations.
- **Multi-tenancy** : isolation stricte par élève, puis par matière (PostgreSQL, ChromaDB, MinIO, JWT).
- **Authentification & RBAC** : JWT RS256, rôles admin/parent/élève, identifiés par pseudo.
- **Dashboards** : progression élève (scores, exercices tentés, temps), vue parent (lecture seule sur ses enfants).
- **i18n** : français par défaut, anglais (next-intl).
- **Accessibilité** : responsive smartphone/tablette, WCAG 2.1 A.
- **Observabilité** : logs structurés, tracing OpenTelemetry, métriques Prometheus, alerting.

## Hors-scope (out)

- **RGPD / CNIL / données personnelles** : projet local, pas de mise en conformité formelle. Identifiants = pseudo uniquement.
- **Déploiement cloud / production** : tout reste en local (docker-compose). Pas de Kubernetes, pas de CI/CD prod.
- **Paiements / abonnements** : pas de modèle freemium, pas de Stripe. Le produit est gratuit.
- **Rôle enseignant** : seul l'élève upload ses copies d'évaluation ; l'enseignant n'est pas un utilisateur de la plateforme.
- **Intégrations tierces** : pas d'ENT (Pronote, ÉcoleDirecte, Google Classroom), pas de SI externes.
- **App mobile native** : web responsive uniquement.
- **Notifications push / email** : tout reste in-app.
- **Multi-langues UI au-delà de FR/EN** : pas d'autres langues dans le périmètre.

## Métriques de succès

- **Latence chatbot** : P95 < 10s sur la 1ère réponse RAG.
- **Engagement correction progressive** : ≥ 60% de re-tentative après un échec initial.
- **Taux d'extraction score évaluation** : ≥ 90% des copies produisent un score exploitable sans saisie manuelle.
- **Taux d'adoption matière** : ≥ 70% des élèves actifs utilisent au moins 2 matières.
- **Taux d'isolation multi-tenant** : 0 incident d'accès cross-tenant sur les 30 derniers jours (test d'isolation intégré au pipeline).
- **Score Lighthouse Accessibility** : ≥ 90 sur les pages principales.

## Contraintes

> Reprises du `CLAUDE.md` — ne pas dupliquer la spec, juste pointer.

- **Stack** : voir `CLAUDE.md` § Stack Technologique
- **Architecture** : voir `CLAUDE.md` § Architecture Système (superviseur + agents spécialisés + RAG par matière)
- **Multi-tenancy** : voir `CLAUDE.md` § Multi-Tenancy
- **LLM par défaut** : voir `CLAUDE.md` § IA et Agents (Minimax-M3, gratuit, local)
- **Correction progressive** : voir `CLAUDE.md` § Correction Progressive des Exercices
- **i18n / accessibilité / observabilité** : voir `CLAUDE.md` § sections dédiées

## Séquentialité POC

**POC = Maths uniquement.** Le Français arrive en **phase 2 starter** (juste après le POC Maths), pour deux raisons :
1. Le scoring de la rédaction (appréciation LLM) demande une qualité de prompt engineering qui sera mieux testée une fois le RAG stabilisé sur les maths.
2. Le RAG Français a des particularités (textes littéraires longs, citations, niveaux de langue) qui complexifient le pipeline d'indexation.

## Questions ouvertes

- **Format des manuels scolaires** : le POC va-t-il se baser sur des manuels libres de droits (Manuels de maths cycle 4 sur Sésamath) ou sur des manuels uploadés par l'élève uniquement ? → à trancher en phase `ks-research` de la STORY-001.
- **Modèles d'exercices** : pour les problèmes de maths, quel niveau de détail dans l'énoncé ? (Algo à affiner en STORY-016.)
- **Politique de re-tentative** : si un élève échoue 3 fois et obtient la correction complète, doit-on considérer l'exercice comme "raté" pour les stats de progression, ou "réussi après aide" ? → à trancher en phase Research de STORY-017.

## Liens

- Spec technique : `CLAUDE.md`
- Règles de pipeline : `AGENTS.md`
- Stories candidates : `docs/stories.md`
- Roadmap : `docs/roadmap.md`

## Historique des révisions

| Date | Auteur | Changement |
|---|---|---|
| 2026-08-27 | `/ks-init` | Création initiale |
