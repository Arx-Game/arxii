import { toast } from 'sonner';
import { extractErrorMessage } from '@/lib/errors';

interface FormDialogOptions {
  /** Close the dialog. */
  close: () => void;
  /** Clear the form after a success. */
  reset: () => void;
  /** The success toast. */
  success: string;
  /** The toast when the failure carries no readable body. */
  fallback: string;
  /** Receive a DRF error body as per-field errors. */
  onFieldErrors: (data: object) => void;
}

/**
 * The mutation callbacks a form dialog shares (#4193): success closes, resets
 * and toasts; a 403 closes with one word; a DRF response body becomes per-field
 * errors; anything else is a toast with the thrown message or the fallback.
 * `err` is the raw `{status, response}` the fetch layer rejects with.
 */
export function formDialogCallbacks(opts: FormDialogOptions): {
  onSuccess: () => void;
  onError: (err: unknown) => void;
} {
  return {
    onSuccess: () => {
      opts.close();
      opts.reset();
      toast.success(opts.success);
    },
    onError: (err) => handleFormMutationError(err, opts),
  };
}

function handleFormMutationError(err: unknown, opts: FormDialogOptions): void {
  const fetchErr = err as { status?: number; response?: Response };
  if (fetchErr.status === 403) {
    toast.error('Permission denied.');
    opts.close();
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
