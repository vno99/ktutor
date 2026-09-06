import MarkdownContent from '@/components/MarkdownContent';
import { useTranslations } from 'next-intl';

export default function DocsPage() {
  const t = useTranslations('docs');

  return (
    <main className="max-w-4xl mx-auto px-6 py-12 bg-canvas text-text-primary">
      <h1 className="text-3xl font-bold tracking-tight mb-2">{t('title')}</h1>
      <p className="text-text-secondary mb-8">{t('subtitle')}</p>

      <nav aria-label={t('navAria')} className="mb-10 p-6 rounded-lg bg-surface border border-border">
        <h2 className="text-xl font-semibold mb-4">{t('navTitle')}</h2>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <li><a href="#creer-compte" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Compte</a></li>
          <li><a href="#upload-document" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Upload</a></li>
          <li><a href="#chat" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Chat</a></li>
          <li><a href="#generer-exercice" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Exercice</a></li>
          <li><a href="#repondre" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Réponse</a></li>
          <li><a href="#dashboard" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Élève — Dashboard</a></li>
          <li><a href="#lier-enfant" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Parent — Enfant</a></li>
          <li><a href="#voir-progression" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Parent — Progrès</a></li>
          <li><a href="#gerer-utilisateurs" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Admin — Utilisateurs</a></li>
          <li><a href="#apercu-flux" className="block px-3 py-2 rounded-md hover:bg-surface-subtle">Admin — Flux</a></li>
        </ul>
      </nav>

      <section className="space-y-12">
        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <MarkdownContent filePath="eleve.md" />
        </article>
        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <MarkdownContent filePath="parent.md" />
        </article>
        <article className="p-6 rounded-lg bg-surface border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <MarkdownContent filePath="admin.md" />
        </article>
      </section>
    </main>
  );
}
