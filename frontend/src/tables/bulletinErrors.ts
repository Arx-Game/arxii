import { ApiError } from '@/lib/errors';

/**
 * DRF field-error shape the bulletin forms render (fields + non_field_errors
 * + detail). Keyed loosely so both post and reply forms can share the mapper.
 */
export interface BulletinFieldErrors {
  [field: string]: string[] | string | undefined;
  non_field_errors?: string[];
  detail?: string;
}

/**
 * Map a thrown error into the field-error shape (2026-07 audit).
 *
 * The bulletin forms previously read `err.response` — a property no thrown
 * error ever had (the api layer threw bare `new Error('Failed to…')`), so
 * every create/edit failure was completely silent. Now the api layer throws
 * `ApiError`, which carries the DRF `fieldErrors` and a human `message`.
 */
export function bulletinErrorsFrom(err: unknown): BulletinFieldErrors {
  if (err instanceof ApiError) {
    if (err.fieldErrors) return err.fieldErrors;
    return { detail: err.message };
  }
  return { detail: err instanceof Error ? err.message : 'Something went wrong.' };
}
