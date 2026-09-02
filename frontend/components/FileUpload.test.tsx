import { describe, it, expect, vi, afterEach } from 'vitest';
import { createRef } from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { FileUpload } from './FileUpload';

/*
 * Unit tests for the extended <FileUpload> (s11c).
 *
 * Behaviour pinned by the plan T3.1 (11 cases):
 *  (a) renders a focusable <label htmlFor="…"> and an sr-only <input type="file" id="…">
 *  (b) clic on the label triggers the input click
 *  (c) input change -> onFileSelect(file)
 *  (d) input change with no file -> onFileSelect(null)
 *  (e) drag over applies border-primary bg-primary/5 on the drop zone
 *  (f) drop of a File -> onFileSelect(file)
 *  (g) drop of 2 files -> onFileSelect called with the first one only
 *  (h) drag leave removes the highlight
 *  (i) when selectedFile is not null: render Card with Lucide icon, name, size, Retirer button
 *  (j) clic on Retirer -> onFileSelect(null)
 *  (k) prop `disabled` blocks drop (no onFileSelect call)
 */

const messages = {
  upload: {
    title: 'Uploader un document',
    subtitle: 'subtitle',
    subjectLabel: 'Matière',
    subjectMaths: 'Mathématiques',
    subjectFrancais: 'Français',
    dropZoneLabel: 'Glisse ton fichier ici ou clique pour parcourir',
    dropZoneHelp: 'PDF, image, texte (max {maxSize} MB)',
    chooseFile: 'Choisir un fichier',
    takePhoto: 'Prendre une photo',
    send: 'Envoyer',
    sending: 'Envoi en cours…',
    removeFileAria: 'Retirer le fichier',
    removeFile: 'Retirer',
    fileSize: '{size} MB',
    noPseudo: 'Choisis un pseudo pour commencer',
    success: 'Document indexé : {name} ({chunks} chunks)',
    manualReview: 'OCR peu fiable',
    uploadAnother: 'Uploader un autre document',
    retry: 'Réessayer',
    error413: 'Fichier trop volumineux (max {maxSize} MB).',
    error415: 'Extension non supportée.',
    errorInvalidPseudo: 'Pseudo invalide.',
    errorOcrFailure: 'Échec de l\'OCR.',
    errorStorageFailure: 'Erreur serveur.',
    errorNetwork: 'Erreur réseau.',
    errorCode: 'Code : {code}',
  },
};

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="fr" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

function makeFile(name: string, type: string, sizeBytes: number): File {
  // Buffer of zero bytes of the given size; jsdom ignores the content, we
  // just need the size to be reported.
  const buffer = new Uint8Array(sizeBytes);
  const file = new File([buffer], name, { type });
  return file;
}

afterEach(() => {
  cleanup();
});

describe('FileUpload (extended)', () => {
  it('(a) renders a focusable <label htmlFor> paired with an sr-only <input type="file">', () => {
    renderWithIntl(
      <FileUpload
        id="upload-file"
        accept=".pdf,.png,.jpg,.jpeg,.txt"
        onFileSelect={() => {}}
        label="Glisse ton fichier ici ou clique pour parcourir"
      />,
    );
    const input = document.getElementById('upload-file') as HTMLInputElement;
    expect(input).not.toBeNull();
    expect(input.type).toBe('file');
    expect(input.accept).toBe('.pdf,.png,.jpg,.jpeg,.txt');
    expect(input.className).toContain('sr-only');
    const label = document.querySelector('label[for="upload-file"]') as HTMLLabelElement;
    expect(label).not.toBeNull();
    // The drop zone is a <label> (not a <div onClick>) — focusable via htmlFor.
    expect(label.tagName).toBe('LABEL');
  });

  it('(b) clicking the visible label triggers a click on the underlying input', () => {
    renderWithIntl(
      <FileUpload
        id="upload-file-b"
        onFileSelect={() => {}}
        label="drop"
      />,
    );
    const input = document.getElementById('upload-file-b') as HTMLInputElement;
    const label = document.querySelector('label[for="upload-file-b"]') as HTMLLabelElement;
    const clickSpy = vi.fn();
    input.addEventListener('click', clickSpy);
    fireEvent.click(label);
    // jsdom does not auto-forward label.click to input.click, but
    // dispatching a real click event on the label does reach the input
    // via the standard <label htmlFor> association.
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it('(c) input change calls onFileSelect with the chosen File', () => {
    const onFileSelect = vi.fn();
    renderWithIntl(
      <FileUpload
        id="upload-file-c"
        onFileSelect={onFileSelect}
        label="drop"
      />,
    );
    const input = document.getElementById('upload-file-c') as HTMLInputElement;
    const file = makeFile('cours.pdf', 'application/pdf', 1024);
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFileSelect).toHaveBeenCalledTimes(1);
    expect(onFileSelect).toHaveBeenCalledWith(file);
  });

  it('(d) input change with no file calls onFileSelect(null)', () => {
    const onFileSelect = vi.fn();
    renderWithIntl(
      <FileUpload
        id="upload-file-d"
        onFileSelect={onFileSelect}
        label="drop"
      />,
    );
    const input = document.getElementById('upload-file-d') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(onFileSelect).toHaveBeenCalledWith(null);
  });

  it('(e) drag over applies bg-primary/5 on the drop zone', () => {
    renderWithIntl(
      <FileUpload
        id="upload-file-e"
        onFileSelect={() => {}}
        label="drop"
      />,
    );
    const label = document.querySelector('label[for="upload-file-e"]') as HTMLLabelElement;
    expect(label.className).not.toContain('bg-primary/5');
    fireEvent.dragOver(label, { dataTransfer: { files: [] } });
    expect(label.className).toContain('bg-primary/5');
  });

  it('(f) drop of a File calls onFileSelect(file)', () => {
    const onFileSelect = vi.fn();
    renderWithIntl(
      <FileUpload
        id="upload-file-f"
        onFileSelect={onFileSelect}
        label="drop"
      />,
    );
    const label = document.querySelector('label[for="upload-file-f"]') as HTMLLabelElement;
    const file = makeFile('cours.pdf', 'application/pdf', 2048);
    const dataTransfer = {
      files: [file],
      types: ['Files'],
    };
    fireEvent.drop(label, { dataTransfer });
    expect(onFileSelect).toHaveBeenCalledTimes(1);
    expect(onFileSelect).toHaveBeenCalledWith(file);
  });

  it('(g) drop of 2 files calls onFileSelect with the FIRST file only', () => {
    const onFileSelect = vi.fn();
    renderWithIntl(
      <FileUpload
        id="upload-file-g"
        onFileSelect={onFileSelect}
        label="drop"
      />,
    );
    const label = document.querySelector('label[for="upload-file-g"]') as HTMLLabelElement;
    const file1 = makeFile('a.pdf', 'application/pdf', 1024);
    const file2 = makeFile('b.pdf', 'application/pdf', 1024);
    const dataTransfer = {
      files: [file1, file2],
      types: ['Files'],
    };
    fireEvent.drop(label, { dataTransfer });
    expect(onFileSelect).toHaveBeenCalledTimes(1);
    expect(onFileSelect).toHaveBeenCalledWith(file1);
  });

  it('(h) drag leave removes the bg-primary/5 highlight', () => {
    renderWithIntl(
      <FileUpload
        id="upload-file-h"
        onFileSelect={() => {}}
        label="drop"
      />,
    );
    const label = document.querySelector('label[for="upload-file-h"]') as HTMLLabelElement;
    fireEvent.dragOver(label, { dataTransfer: { files: [] } });
    expect(label.className).toContain('bg-primary/5');
    fireEvent.dragLeave(label);
    expect(label.className).not.toContain('bg-primary/5');
  });

  it('(i) when selectedFile is not null, renders a Card with icon, name, size and a Retirer button', () => {
    const onFileSelect = vi.fn();
    // 1.234567 MB — without maximumFractionDigits, Intl would render
    // "1,235" (3 decimals) or "1,234567" (full precision). The contract
    // is exactly 1 decimal place.
    const file = makeFile('cours.pdf', 'application/pdf', 1.234567 * 1024 * 1024);
    renderWithIntl(
      <FileUpload
        id="upload-file-i"
        onFileSelect={onFileSelect}
        label="drop"
        selectedFile={file}
      />,
    );
    expect(screen.getByText('cours.pdf')).toBeInTheDocument();
    // Intl.NumberFormat('fr', { maximumFractionDigits: 1 }).format(1.234567) === '1,2'
    expect(screen.getByText(/1,2\s*MB/i)).toBeInTheDocument();
    const retirer = screen.getByRole('button', { name: 'Retirer le fichier' });
    expect(retirer).toBeInTheDocument();
  });

  it('(j) clicking Retirer calls onFileSelect(null)', () => {
    const onFileSelect = vi.fn();
    const file = makeFile('cours.pdf', 'application/pdf', 1024);
    renderWithIntl(
      <FileUpload
        id="upload-file-j"
        onFileSelect={onFileSelect}
        label="drop"
        selectedFile={file}
      />,
    );
    screen.getByRole('button', { name: 'Retirer le fichier' }).click();
    expect(onFileSelect).toHaveBeenCalledWith(null);
  });

  it('(k) disabled prop blocks drag & drop (no onFileSelect call)', () => {
    const onFileSelect = vi.fn();
    renderWithIntl(
      <FileUpload
        id="upload-file-k"
        onFileSelect={onFileSelect}
        label="drop"
        disabled
      />,
    );
    const label = document.querySelector('label[for="upload-file-k"]') as HTMLLabelElement;
    const file = makeFile('cours.pdf', 'application/pdf', 1024);
    const dataTransfer = {
      files: [file],
      types: ['Files'],
    };
    fireEvent.drop(label, { dataTransfer });
    expect(onFileSelect).not.toHaveBeenCalled();
    // Drag over is also blocked.
    fireEvent.dragOver(label, { dataTransfer: { files: [] } });
    expect(label.className).not.toContain('bg-primary/5');
  });

  it('(l) forwardRef exposes the underlying picker <input> to the parent', () => {
    const ref = createRef<HTMLInputElement>();
    renderWithIntl(
      <FileUpload
        id="upload-file-l"
        ref={ref}
        onFileSelect={() => {}}
        label="drop"
      />,
    );
    expect(ref.current).not.toBeNull();
    expect(ref.current?.tagName).toBe('INPUT');
    expect(ref.current?.type).toBe('file');
  });
});
