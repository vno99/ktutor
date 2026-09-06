import { readFileSync } from 'fs';
import path from 'path';

interface MarkdownContentProps {
  filePath: string;
  locale?: 'fr' | 'en';
}

export default function MarkdownContent({ filePath, locale = 'fr' }: MarkdownContentProps) {
  // Read markdown file statically (server component)
  const fileName = locale === 'en' ? filePath.replace('.md', '.en.md') : filePath;
  const fullPath = path.resolve(__dirname, "..", "..", "docs", "user-guide", fileName);
  let content = '';
  try {
    content = readFileSync(fullPath, 'utf-8');
  } catch {
    // Fallback to base file if localized version missing
    content = readFileSync(path.resolve(__dirname, '..', '..', 'docs', 'user-guide', filePath), 'utf-8');
  }

  // Minimal markdown-to-HTML conversion for the user-guide format
  const html = content
    .replace(/\n---\n/g, '<hr />')
    .replace(/^### (.+?) <a id="(.+?)"><\/a>$/gm, '<h3 id="$2">$1</h3>')
    .replace(/^### (.+)$/gm, '<h3 id="$1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 id="$1">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 id="$1">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .split('\n')
    .map((line) => {
      if (line.trim() === '') return '<br />';
      return `<p>${line.trim()}</p>`;
    })
    .join('');

  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
