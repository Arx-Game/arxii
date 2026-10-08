import { toast } from 'sonner';
import { extractErrorMessage } from '@/lib/errors';

/**
 * The error branches a form dialog's mutation shares (#4193): a 403 closes the
 * dialog with one word, a DRF response body becomes per-field errors, and
 * anything else is a toast with the thrown message or the caller's fallback.
 * `err` is the raw `{status, response}` the fetch layer rejects with.
 */
export function handleFormMutationError(
  err: unknown,
  opts: { onForbidden: () => void; onFieldErrors: (data: object) => void; fallback: string }
): void {
  const fetchErr = err as { status?: number; response?: Response };
  if (fetchErr.status === 403) {
    toast.error('Permission denied.');
    opts.onForbidden();
    return;
  }
  if (fetchErr.response) {
    fetchErr.response
      .json()
      .then((data: unknown) => {
        if (data && typeof data === 'object') opts.onFieldErrors(data);
      })
      .catch(() => toast.error(opts.fallback));
    return;
  }
  toast.error(extractErrorMessage(err, opts.fallback));
}
