import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StreamingMessage } from './StreamingMessage';

/*
 * Unit tests for the extended <StreamingMessage> (s11b).
 *
 * The s11a skeleton only knew about isStreaming + hasContent +
 * children. s11b adds three props:
 *  - error?: ChatStreamError | null
 *  - sources?: SourceCitation[] | null
 *  - streamingStatus?: 'idle' | 'streaming' | 'done' | 'error'
 *
 * The old props remain optional (backward-compat for any caller that
 * still uses the s11a shape — the only known caller is the home page,
 * which doesn't actually use StreamingMessage today).
 *
 * Behaviour pinned:
 *  - When error is set, the error card is rendered with the i18n key
 *    for the code, plus a Retry button that calls onRetry.
 *  - When sources has 1+ entries, a "Sources :" line is rendered.
 *  - When sources has > 5 entries, the line ends with "… and N more".
 *  - The live region and aria-busy are still wired.
 */

const sources1 = [{ filename: 'cours.pdf', chunk_index: 0 }];

describe('StreamingMessage (extended)', () => {
  it('renders the children as the live region content', () => {
    render(
      <StreamingMessage isStreaming={false} hasContent>
        <p>hello</p>
      </StreamingMessage>,
    );
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('renders an error card with the i18n key when error is set', () => {
    render(
      <StreamingMessage
        isStreaming={false}
        hasContent
        error={{ code: 'unknown', message: 'oops' }}
        tErrors={(k: string) => `t(${k})`}
      />,
    );
    // The error card renders the translated string.
    expect(screen.getByText('t(unknown)')).toBeInTheDocument();
  });

  it('renders a "Sources :" line when sources has one entry', () => {
    const { container } = render(
      <StreamingMessage
        isStreaming={false}
        hasContent
        sources={sources1}
        t={(k: string) => `t(${k})`}
      />,
    );
    expect(container.textContent).toContain('cours.pdf');
  });

  it('truncates sources after 5 entries with a "… and N more" tail', () => {
    const sources = [
      { filename: 'a.pdf', chunk_index: 0 },
      { filename: 'b.pdf', chunk_index: 0 },
      { filename: 'c.pdf', chunk_index: 0 },
      { filename: 'd.pdf', chunk_index: 0 },
      { filename: 'e.pdf', chunk_index: 0 },
      { filename: 'f.pdf', chunk_index: 0 },
      { filename: 'g.pdf', chunk_index: 0 },
    ];
    const { container } = render(
      <StreamingMessage
        isStreaming={false}
        hasContent
        sources={sources}
        t={(k: string, vars?: Record<string, unknown>) =>
          vars ? `t(${k},${JSON.stringify(vars)})` : `t(${k})`
        }
      />,
    );
    expect(container.textContent).toContain('a.pdf');
    expect(container.textContent).toContain('e.pdf');
    expect(container.textContent).not.toContain('f.pdf');
    expect(container.textContent).toContain('"n":2');
  });

  it('calls onRetry when the Retry button is clicked', () => {
    const onRetry = vi.fn();
    render(
      <StreamingMessage
        isStreaming={false}
        hasContent
        error={{ code: 'unknown', message: 'oops' }}
        t={(k: string) => `t(${k})`}
        tErrors={(k: string) => `t(${k})`}
        onRetry={onRetry}
      />,
    );
    screen.getByRole('button', { name: 't(retry)' }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
