import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';

export default function DocsPage() {
  const t = useTranslations('docs');

  const sections = [
    { id: 'creer-compte', labelFr: "Créer un compte", labelEn: 'Create an account', file: 'eleve.md' },
    { id: 'upload-document', labelFr: 'Uploader un document', labelEn: 'Upload a document', file: 'eleve.md' },
    { id: 'chat', labelFr: 'Dialoguer avec le chatbot', labelEn: 'Chat', file: 'eleve.md' },
    { id: 'generer-exercice', labelFr: 'Générer un exercice', labelEn: 'Generate an exercise', file: 'eleve.md' },
    { id: 'repondre', labelFr: 'Soumettre une réponse', labelEn: 'Submit an answer', file: 'eleve.md' },
    { id: 'dashboard', labelFr: 'Tableau de bord', labelEn: 'Dashboard', file: 'eleve.md' },
    { id: 'lier-enfant', labelFr: 'Lier un enfant', labelEn: 'Link a child', file: 'parent.md' },
    { id: 'voir-progression', labelFr: 'Voir la progression', labelEn: 'View progress', file: 'parent.md' },
    { id: 'gerer-utilisateurs', labelFr: 'Gérer les utilisateurs', labelEn: 'Manage users', file: 'admin.md' },
    { id: 'apercu-flux', labelFr: 'Aperçu des flux', labelEn: 'Overview of flows', file: 'admin.md' },
  ];

  return (
    <main className="max-w-4xl mx-auto px-6 py-12 bg-canvas text-text-primary">
      <h1 className="text-3xl font-bold tracking-tight mb-2">{t('title')}</h1>
      <p className="text-text-secondary mb-8">{t('subtitle')}</p>

      <nav aria-label={t('navAria')} className="mb-10 p-6 rounded-lg bg-surface border border-border">
        <h2 className="text-xl font-semibold mb-4">{t('navTitle')}</h2>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          {sections.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="block px-3 py-2 rounded-md hover:bg-surface-subtle text-text-primary hover:text-text-secondary no-underline focus:outline-none focus:ring-2 focus:ring-primary focus-visible:ring-2 focus-visible:ring-offset-2"
              >
                <span className="font-medium">{s.labelFr}</span>
                <span className="ml-1 text-text-tertiary text-xs">({s.file})</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <section className="space-y-12">
        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h2 className="text-2xl font-semibold mb-4">Élève / Student</h2>
          <div className="prose prose-sm max-w-none text-text-secondary leading-relaxed space-y-6">
            <div id="creer-compte">
              <h3 className="text-lg font-medium text-text-primary mb-2">Créer un compte / Create an account</h3>
              <p>Créez votre compte via <code>/auth/login</code> ou <code>/auth/register</code>. Utilisez un pseudo (pas de données personnelles réelles). Une fois connecté, votre <code>pseudo</code> est stocké dans le JWT.</p>
            </div>
            <div id="upload-document">
              <h3 className="text-lg font-medium text-text-primary mb-2">Uploader un document / Upload a document</h3>
              <p>Depuis le tableau de bord élève (<code>/dashboard/eleve</code>), utilisez le bouton d'upload pour envoyer un cours (PDF, DOCX, image). Le fichier est indexé dans ChromaDB via la tâche Celery (OCR + chunking).</p>
            </div>
            <div id="chat">
              <h3 className="text-lg font-medium text-text-primary mb-2">Dialoguer avec le chatbot / Chat</h3>
              <p>Accédez au chat (<code>/chat</code>) pour poser des questions sur vos cours. Le super-agent LangGraph route vers l'agent compétent et répond en streaming (SSE).</p>
            </div>
            <div id="generer-exercice">
              <h3 className="text-lg font-medium text-text-primary mb-2">Générer un exercice / Generate an exercise</h3>
              <p>Depuis le dashboard ou le chat, demandez la génération d'un exercice (<code>/exercises/generate</code>). Choisissez la matière, le sujet, la difficulté et le type (QCM, problème, flashcards, rédaction).</p>
            </div>
            <div id="repondre">
              <h3 className="text-lg font-medium text-text-primary mb-2">Soumettre une réponse / Submit an answer</h3>
              <p>Téléchargez votre réponse (texte ou photo manuscrite) via <code>/exercises/submit</code>. Le système évalue automatiquement : si le score est ≥ 80 %, la correction complète est dévoilée ; sinon, seuls des indices sont donnés. Après 3 tentatives, la correction complète est dévoilée.</p>
            </div>
            <div id="dashboard">
              <h3 className="text-lg font-medium text-text-primary mb-2">Tableau de bord / Dashboard</h3>
              <p>Le tableau de bord élève (<code>/dashboard/eleve</code>) affiche vos métriques : points, historique des exercices, évaluations et récompenses.</p>
            </div>
          </div>
        </article>

        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h2 className="text-2xl font-semibold mb-4">Parent / Parent</h2>
          <div className="prose prose-sm max-w-none text-text-secondary leading-relaxed space-y-6">
            <div id="lier-enfant">
              <h3 className="text-lg font-medium text-text-primary mb-2">Lier un enfant / Link a child</h3>
              <p>Un parent crée son compte (<code>/auth/login</code> avec rôle <code>parent</code>), puis lie son enfant via <code>/users/&#123;parent_id&#125;/children</code> (POST). L'enfant doit avoir un <code>pseudo</code> existant.</p>
            </div>
            <div id="voir-progression">
              <h3 className="text-lg font-medium text-text-primary mb-2">Voir la progression / View progress</h3>
              <p>Le tableau de bord parent (<code>/dashboard/parent</code>) affiche la progression des enfants liés : points gagnés (<code>/rewards</code>), résultats d'évaluations (<code>/evaluations</code>), historique des exercices (<code>/exercises/history</code>). Les données sont isolées par <code>student_pseudo</code>.</p>
            </div>
          </div>
        </article>

        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h2 className="text-2xl font-semibold mb-4">Admin / Admin</h2>
          <div className="prose prose-sm max-w-none text-text-secondary leading-relaxed space-y-6">
            <div id="gerer-utilisateurs">
              <h3 className="text-lg font-medium text-text-primary mb-2">Gérer les utilisateurs / Manage users</h3>
              <p>L'administrateur accède au tableau de bord admin (<code>/dashboard/admin</code>) et aux endpoints <code>/users</code>. Il peut créer un utilisateur, modifier son rôle et lier parent-enfant. Toutes les requêtes filtrent par <code>student_pseudo</code> (multi-tenancy).</p>
            </div>
            <div id="apercu-flux">
              <h3 className="text-lg font-medium text-text-primary mb-2">Aperçu des flux / Overview of flows</h3>
              <p>Les fonctionnalités principales sont couvertes dans le guide élève : création de compte, upload, chat, génération d'exercices, soumission de réponses, tableau de bord, et correction progressive.</p>
            </div>
          </div>
        </article>
      </section>
    </main>
  );
}
