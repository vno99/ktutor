import { readFileSync } from 'fs';
import path from 'path';

interface MarkdownContentProps {
  filePath: string;
  locale?: 'fr' | 'en';
}

export default function MarkdownContent({ filePath }: MarkdownContentProps) {
  // Files are at frontend/docs/user-guide/ (static, not under [locale] segment)
  const fullPath = path.resolve(process.cwd(), 'docs', 'user-guide', filePath);
  let content = '';
  try {
    content = readFileSync(fullPath, 'utf-8');
  } catch {
    content = `<p>Content not found: ${filePath}</p>`;
  }

  // Minimal markdown-to-HTML conversion for the user-guide format
  const html = content
    .replace(/\n---\n/g, '<hr />')
    .replace(/^### (.+?) <a id="(.+?)"><\/a>$/gm, '<h3 id="$2">$1</h3>')
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
