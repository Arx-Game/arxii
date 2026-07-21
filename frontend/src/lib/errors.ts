/**
 * Shared error helpers (#895). Consolidates the `extractErrorMessage` copy
 * that was duplicated across ~10 magic/ritual dialogs, plus the api-layer
 * `{detail}` parse-and-throw pattern: `readErrorDetail` is the single home for
 * the per-module `parseErrorDetail` copies, swept onto it in #1195.
 *
 * 2026-07 audit: errors thrown here are now `ApiError`s carrying the HTTP
 * status and any DRF field errors, so downstream code can distinguish 4xx
 * from 5xx (React Query's retry policy skips 4xx) and dialogs can surface
 * per-field validation detail instead of a generic string.
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
 * A non-ok API response, preserving what the generic string-throw pattern
 * discarded: the HTTP status, the DRF `{detail}`, and DRF field-validation
 * errors (`{field: ["msg", …]}`). `message` is always human-readable — the
 * detail when present, else flattened field errors, else the caller's
 * fallback — so existing `err.message` render sites keep working unchanged.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  readonly fieldErrors: Record<string, string[]> | null;

  constructor(
    message: string,
    opts: { status: number; detail?: string | null; fieldErrors?: Record<string, string[]> | null }
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.detail = opts.detail ?? null;
    this.fieldErrors = opts.fieldErrors ?? null;
  }
}

/** "name: this field is required; tier: must be positive" from a DRF error body. */
function flattenFieldErrors(fieldErrors: Record<string, string[]>): string {
  return Object.entries(fieldErrors)
    .map(([field, messages]) => `${field}: ${messages.join(' ')}`)
    .join('; ');
}

/**
 * Collect DRF validation errors (`{field: ["msg", ...]}`, incl.
 * `non_field_errors`) from a parsed response body. Returns `null` when no
 * field-level errors are present (e.g. a bare `{detail}` or empty body).
 */
function collectFieldErrors(body: Record<string, unknown>): Record<string, string[]> | null {
  const collected: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(body)) {
    if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
      collected[key] = value as string[];
    }
  }
  return Object.keys(collected).length > 0 ? collected : null;
}

/**
 * Parse a DRF error body (already awaited) into `{detail, fieldErrors}`.
 * The `{detail}` string wins when present; otherwise DRF field-validation
 * errors are collected. Returns both `null` for non-object/empty bodies.
 */
function parseErrorBody(data: unknown): {
  detail: string | null;
  fieldErrors: Record<string, string[]> | null;
} {
  if (!data || typeof data !== 'object') return { detail: null, fieldErrors: null };
  const body = data as Record<string, unknown>;
  if (typeof body.detail === 'string' && body.detail.trim()) {
    return { detail: body.detail, fieldErrors: null };
  }
  return { detail: null, fieldErrors: collectFieldErrors(body) };
}

/**
 * Parse a non-ok DRF Response and throw an `ApiError` carrying status,
 * `{detail}`, and any field-validation errors. The thrown message prefers
 * detail, then flattened field errors, then `fallback`.
 */
export async function throwApiError(res: Response, fallback: string): Promise<never> {
  let detail: string | null = null;
  let fieldErrors: Record<string, string[]> | null = null;
  try {
    const data: unknown = await res.json();
    ({ detail, fieldErrors } = parseErrorBody(data));
  } catch {
    // body wasn't JSON; keep the fallback
  }
  const message = detail ?? (fieldErrors ? flattenFieldErrors(fieldErrors) : fallback);
  throw new ApiError(message, { status: res.status, detail, fieldErrors });
}

/**
 * Parse a non-ok DRF Response's `{detail}` and throw an error carrying it,
 * falling back to `fallback` when the body is missing/blank/non-JSON.
 * (Alias of `throwApiError` — kept for its many existing call sites; both
 * now throw status-carrying `ApiError`s with field-error flattening.)
 */
export async function readErrorDetail(res: Response, fallback: string): Promise<never> {
  return throwApiError(res, fallback);
}
