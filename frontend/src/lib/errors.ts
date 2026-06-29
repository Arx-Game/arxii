/**
 * Shared error helpers (#895). Consolidates the `extractErrorMessage` copy
 * that was duplicated across ~10 magic/ritual dialogs, plus the api-layer
 * `{detail}` parse-and-throw pattern: `readErrorDetail` is the single home for
 * the per-module `parseErrorDetail` copies, swept onto it in #1195.
 */

/** Best-effort human-readable message from an unknown thrown value. */
export function extractErrorMessage(
  error: unknown,
  fallback = 'An unexpected error occurred.'
): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/**
 * Parse a non-ok DRF Response's `{detail}` and throw an Error carrying it,
 * falling back to `fallback` when the body is missing/blank/non-JSON.
 */
export async function readErrorDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const data = (await res.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // body wasn't JSON; keep the fallback
  }
  throw new Error(detail);
}
