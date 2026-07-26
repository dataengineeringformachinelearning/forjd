/**
 * One-shot reload when a deploy leaves the tab on stale lazy chunks.
 * Mirrors DEML recovery — FORJD landing is eager today; keep this ready for lazy routes.
 */

const CHUNK_RELOAD_KEY = 'forjd_chunk_reload';

export function isChunkLoadError(error: unknown): boolean {
  const candidates: string[] = [];
  if (typeof error === 'string') {
    candidates.push(error);
  } else if (error && typeof error === 'object') {
    const err = error as {
      message?: unknown;
      name?: unknown;
      error?: { message?: unknown };
    };
    if (err.message != null) candidates.push(String(err.message));
    if (err.name != null) candidates.push(String(err.name));
    if (err.error?.message != null) candidates.push(String(err.error.message));
  }
  const text = candidates.join(' ').toLowerCase();
  return (
    text.includes('failed to fetch dynamically imported module') ||
    text.includes('error loading dynamically imported module') ||
    text.includes('importing a module script failed') ||
    text.includes('failed to load module script')
  );
}

/** Returns true when a reload was scheduled (caller should stop further handling). */
export function reloadOnceOnChunkError(error: unknown): boolean {
  if (typeof window === 'undefined' || typeof sessionStorage === 'undefined') {
    return false;
  }
  if (!isChunkLoadError(error)) {
    return false;
  }
  try {
    if (sessionStorage.getItem(CHUNK_RELOAD_KEY) === '1') {
      sessionStorage.removeItem(CHUNK_RELOAD_KEY);
      return false;
    }
    sessionStorage.setItem(CHUNK_RELOAD_KEY, '1');
  } catch {
    // sessionStorage may be blocked; still attempt a single reload.
  }
  window.location.reload();
  return true;
}
