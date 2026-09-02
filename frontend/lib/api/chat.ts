/*
 * chat.ts — pure helpers for the chat stream.
 *
 * The contract this module consumes (frozen in s09) is documented at:
 *  - backend/app/api/chat/sse.py:21-30  — format_sse():
 *      `data: <json>\n\n` with `ensure_ascii=False`.
 *  - backend/app/api/chat/router.py:99-112 — event_generator():
 *      three event shapes: {token}, {done, sources}, {error, code}.
 *  - backend/app/api/chat/schemas.py:34-77 — request body and codes.
 *
 * Only the parser is exported. The store in lib/stores/chatStore.ts
 * calls parseSSEChunk on each text buffer it accumulates from
 * response.body.getReader(). Parsing is kept pure and synchronous
 * so it can be unit-tested without a fetch polyfill.
 */

export type ChatStreamErrorCode =
  | 'cross_tenant'
  | 'no_subject'
  | 'invalid_pseudo'
  | 'unknown'
  // Frontend-only codes for stream-level errors (no backend code):
  | 'network' // HTTP-level failure (e.g. 5xx, connection refused)
  | 'lost'; // connection cut mid-stream

export type SourceCitation = {
  filename: string;
  chunk_index: number;
};

export type SSEEvent =
  | { type: 'token'; content: string }
  | { type: 'done'; sources: SourceCitation[] }
  | { type: 'error'; error: string; code: ChatStreamErrorCode };

/**
 * parseSSEChunk — turn a text buffer (one or more `data: <json>\n\n`
 * frames concatenated) into a flat list of typed events.
 *
 * Lines that do not start with `data: ` are ignored (heartbeats,
 * comments, blank lines). Empty `data:` lines are ignored. Frames
 * whose JSON fails to parse are dropped — the caller's reader
 * will continue on the next chunk, and a single bad frame must
 * never kill the stream.
 */
export function parseSSEChunk(raw: string): SSEEvent[] {
  if (raw.length === 0) return [];
  const events: SSEEvent[] = [];
  for (const block of raw.split('\n\n')) {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice('data:'.length).trim();
      if (payload.length === 0) continue;
      let parsed: unknown;
      try {
        parsed = JSON.parse(payload);
      } catch {
        // Malformed JSON — skip this frame, the stream continues.
        continue;
      }
      if (!parsed || typeof parsed !== 'object') continue;
      const obj = parsed as Record<string, unknown>;
      if (typeof obj.token === 'string') {
        events.push({ type: 'token', content: obj.token });
      } else if (obj.done === true) {
        const sources = Array.isArray(obj.sources)
          ? obj.sources.filter(
              (s): s is SourceCitation =>
                !!s &&
                typeof s === 'object' &&
                typeof (s as SourceCitation).filename === 'string' &&
                typeof (s as SourceCitation).chunk_index === 'number',
            )
          : [];
        events.push({ type: 'done', sources });
      } else if (typeof obj.error === 'string' && typeof obj.code === 'string') {
        // The backend only emits the four narrow codes; anything else
        // collapses to 'unknown' so the page always has a key to map.
        const code: ChatStreamErrorCode =
          obj.code === 'cross_tenant' ||
          obj.code === 'no_subject' ||
          obj.code === 'invalid_pseudo' ||
          obj.code === 'unknown'
            ? obj.code
            : 'unknown';
        events.push({ type: 'error', error: obj.error, code });
      }
    }
  }
  return events;
}
