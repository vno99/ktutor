import { describe, it, expect } from 'vitest';
import { parseSSEChunk } from './chat';

/*
 * Unit tests for the pure SSE parser (s11b).
 *
 * The parser is intentionally synchronous and pure: it takes a raw
 * text buffer (one or more SSE frames concatenated) and returns a
 * flat list of typed events. The store feeds it chunks as they come
 * off the ReadableStream; the parser never throws — it returns []
 * on malformed JSON so a single bad frame cannot kill the stream.
 *
 * The three event shapes come from the backend contract (s09):
 *  - {token: "..."}  : a chunk of the assistant reply
 *  - {done, sources} : final event, exactly once per stream
 *  - {error, code}   : agent refused the request
 *
 * Comments in the input (`data:` empty, `:` heartbeat) must be
 * ignored, not surfaced as events.
 */

describe('parseSSEChunk', () => {
  it('parses a single {token} event', () => {
    const events = parseSSEChunk('data: {"token":"a"}\n\n');
    expect(events).toEqual([{ type: 'token', content: 'a' }]);
  });

  it('parses an empty {token} as a no-op (does not throw)', () => {
    const events = parseSSEChunk('data: {"token":""}\n\n');
    expect(events).toEqual([{ type: 'token', content: '' }]);
  });

  it('parses a {done, sources} event', () => {
    const events = parseSSEChunk(
      'data: {"done":true,"sources":[{"filename":"x.pdf","chunk_index":0}]}\n\n',
    );
    expect(events).toEqual([
      {
        type: 'done',
        sources: [{ filename: 'x.pdf', chunk_index: 0 }],
      },
    ]);
  });

  it('parses a {error, code} event', () => {
    const events = parseSSEChunk('data: {"error":"oops","code":"unknown"}\n\n');
    expect(events).toEqual([
      { type: 'error', error: 'oops', code: 'unknown' },
    ]);
  });

  it('ignores an empty chunk', () => {
    const events = parseSSEChunk('');
    expect(events).toEqual([]);
  });

  it('ignores an empty `data:` (SSE comment line)', () => {
    const events = parseSSEChunk('data:\n\n');
    expect(events).toEqual([]);
  });

  it('parses multiple events concatenated in one chunk', () => {
    const events = parseSSEChunk(
      'data: {"token":"Une "}\n\n' +
        'data: {"token":"dérivée."}\n\n' +
        'data: {"done":true,"sources":[]}\n\n',
    );
    expect(events).toEqual([
      { type: 'token', content: 'Une ' },
      { type: 'token', content: 'dérivée.' },
      { type: 'done', sources: [] },
    ]);
  });

  it('returns [] on malformed JSON (no crash)', () => {
    const events = parseSSEChunk('data: {not-json}\n\n');
    expect(events).toEqual([]);
  });
});
