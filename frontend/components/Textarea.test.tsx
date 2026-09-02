import { describe, it, expect } from 'vitest';
import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { Textarea } from './Textarea';

/*
 * Unit tests for the shared <Textarea> component (s11b).
 *
 * Behaviour pinned by the plan:
 *  - renders a native <textarea> with the id passed in props
 *  - min-h-24 (4 lines) is on the className
 *  - aria-invalid is wired from the `invalid` prop
 *  - forwardRef<HTMLTextAreaElement> works
 *  - maxLength is forwarded to the native element
 *
 * No decorators: this component is intentionally minimal — its
 * purpose is to give s11b (chat question) and s11c+ (admin forms)
 * a shared, accessible textarea aligned with <Input>.
 */

describe('Textarea', () => {
  it('renders a <textarea> with the provided id', () => {
    render(<Textarea id="chat-question-1" aria-label="question-1" />);
    const ta = screen.getByLabelText('question-1') as HTMLTextAreaElement;
    expect(ta.tagName).toBe('TEXTAREA');
    expect(ta.id).toBe('chat-question-1');
  });

  it('applies min-h-24 to the rendered textarea', () => {
    render(<Textarea id="chat-question-2" aria-label="question-2" />);
    const ta = screen.getByLabelText('question-2');
    expect(ta.className).toContain('min-h-24');
  });

  it('sets aria-invalid="true" when invalid is true', () => {
    render(
      <Textarea id="chat-question-3" aria-label="question-3" invalid />,
    );
    const ta = screen.getByLabelText('question-3');
    expect(ta.getAttribute('aria-invalid')).toBe('true');
  });

  it('omits aria-invalid when invalid is false', () => {
    render(<Textarea id="chat-question-4" aria-label="question-4" />);
    const ta = screen.getByLabelText('question-4');
    expect(ta.hasAttribute('aria-invalid')).toBe(false);
  });

  it('forwards a ref to the underlying <textarea>', () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(
      <Textarea id="chat-question-5" aria-label="question-5" ref={ref} />,
    );
    expect(ref.current).not.toBeNull();
    expect(ref.current?.tagName).toBe('TEXTAREA');
  });

  it('forwards maxLength to the native textarea', () => {
    render(
      <Textarea
        id="chat-question-6"
        aria-label="question-6"
        maxLength={2000}
        defaultValue="hello"
      />,
    );
    const ta = screen.getByLabelText('question-6') as HTMLTextAreaElement;
    expect(ta.maxLength).toBe(2000);
    expect(ta.value).toBe('hello');
  });
});
