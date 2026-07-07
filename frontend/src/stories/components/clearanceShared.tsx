/**
 * Shared helpers for the clearance-action dialogs/buttons (#2001).
 *
 * Extracted to keep duplicated code below SonarCloud's 3% gate — the grant/deny
 * and escalate/revoke pairs were 80%+ identical before this module existed.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

/** Shape of DRF validation error responses. */
export interface DRFFieldErrors {
  detail?: string;
  non_field_errors?: string[];
}

/**
 * Standard error handler for clearance mutations that toast the error.
 * Tries to parse a DRF JSON error body, then falls back to a generic toast.
 */
export function makeClearanceToastHandler(fallback: string) {
  return (err: unknown) => {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            const drf = data as DRFFieldErrors;
            toast.error(drf.detail ?? drf.non_field_errors?.join(' ') ?? fallback);
          })
          .catch(() => toast.error(fallback));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : fallback);
  };
}

// ---------------------------------------------------------------------------
// ClearanceNoteDialog — reusable dialog for note-based clearance actions
// ---------------------------------------------------------------------------

interface ClearanceNoteDialogProps {
  /** Dialog title shown in the header. */
  title: string;
  /** Label for the optional note field. */
  noteLabel: string;
  /** Placeholder for the textarea. */
  placeholder: string;
  /** Text for the submit button. */
  submitLabel: string;
  /** Gerund form for the pending state (e.g. "Granting…"). */
  pendingLabel: string;
  /** Whether the mutation is pending. */
  isPending: boolean;
  /** Called with the trimmed note when the user submits. The dialog closes
   *  itself on success via {@link onSuccess}. */
  onSubmit: (note: string, helpers: { setError: (msg: string) => void; close: () => void }) => void;
  /** Toast message on success. */
  successToast: string;
  /** Fallback error message for inline display. */
  errorFallback: string;
  /** Variant for the submit button. */
  submitVariant?: 'default' | 'destructive';
  /** testId for the trigger button. */
  triggerTestId: string;
  /** Trigger button label. */
  triggerLabel: string;
  /** Variant for the trigger button. */
  triggerVariant?: 'default' | 'outline' | 'destructive';
}

/**
 * Reusable dialog for clearance actions that take an optional note
 * (grant / deny / resolve). The caller provides the mutation and labels;
 * this component owns the open/note/error state and the DRF-error parsing.
 */
export function ClearanceNoteDialog({
  title,
  noteLabel,
  placeholder,
  submitLabel,
  pendingLabel,
  isPending,
  onSubmit,
  triggerTestId,
  triggerLabel,
  triggerVariant,
  submitVariant,
}: ClearanceNoteDialogProps) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setNote('');
      setError('');
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    onSubmit(note.trim(), {
      setError,
      close: () => handleOpenChange(false),
    });
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant={triggerVariant} size="sm" data-testid={triggerTestId}>
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <div className="mt-4 space-y-1.5">
            <Label htmlFor={`${triggerTestId}-note`}>
              {noteLabel} <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id={`${triggerTestId}-note`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder={placeholder}
            />
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          <DialogFooter className="mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" variant={submitVariant} disabled={isPending}>
              {isPending ? pendingLabel : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Helper for note-dialog onError callbacks: parses a DRF JSON error body and
 * calls {@link setError} with the message, or falls back to {@link fallback}.
 */
export function handleInlineError(err: unknown, setError: (msg: string) => void, fallback: string) {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: Response }).response;
    if (response) {
      void response
        .json()
        .then((data: unknown) => {
          const drf = data as DRFFieldErrors;
          setError(drf.detail ?? drf.non_field_errors?.join(' ') ?? fallback);
        })
        .catch(() => setError(fallback));
      return;
    }
  }
  setError(err instanceof Error ? err.message : fallback);
}

// ---------------------------------------------------------------------------
// ClearanceConfirmButton — reusable confirm dialog for no-input actions
// ---------------------------------------------------------------------------

interface ClearanceConfirmButtonProps {
  /** AlertDialog title. */
  title: string;
  /** Description shown below the title. */
  description: string;
  /** Text for the confirm button. */
  confirmLabel: string;
  /** Whether the mutation is pending. */
  isPending: boolean;
  /** Called when the user confirms. */
  onConfirm: () => void;
  /** testId for the trigger button. */
  triggerTestId: string;
  /** Trigger button label. */
  triggerLabel: string;
  /** Gerund form for the pending state (e.g. "Escalating…"). */
  pendingLabel: string;
  /** Extra classes for the trigger button. */
  triggerClassName?: string;
}

/**
 * Reusable confirm-button for clearance actions that need no input
 * (escalate / revoke). Uses an AlertDialog for the confirmation step.
 */
export function ClearanceConfirmButton({
  title,
  description,
  confirmLabel,
  isPending,
  onConfirm,
  triggerTestId,
  triggerLabel,
  pendingLabel,
  triggerClassName,
}: ClearanceConfirmButtonProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={triggerClassName}
          disabled={isPending}
          data-testid={triggerTestId}
        >
          {isPending ? pendingLabel : triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
