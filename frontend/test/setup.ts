import '@testing-library/jest-dom/vitest';

/*
 * jsdom 25 + Node 25 quirk: Node 25 ships a `--localstorage-file`
 * Web Storage shim that pre-installs a non-functional Proxy on
 * ``window.localStorage`` (the actual methods are missing). We
 * detect that case and replace the proxy with a tiny in-memory
 * polyfill so the authStore tests can exercise
 * ``getItem``/``setItem``/``removeItem``/``clear``.
 *
 * Outside this environment, jsdom's native localStorage works and
 * we leave it alone.
 */
if (typeof window !== 'undefined' && window.localStorage && typeof window.localStorage.setItem !== 'function') {
  const mem = new Map<string, string>();
  const proxy: Storage = {
    get length() {
      return mem.size;
    },
    clear() {
      mem.clear();
    },
    getItem(key: string) {
      return mem.has(key) ? (mem.get(key) as string) : null;
    },
    key(index: number) {
      return Array.from(mem.keys())[index] ?? null;
    },
    removeItem(key: string) {
      mem.delete(key);
    },
    setItem(key: string, value: string) {
      mem.set(key, String(value));
    },
  };
  Object.defineProperty(window, 'localStorage', {
    value: proxy,
    configurable: true,
    writable: true,
  });
}
