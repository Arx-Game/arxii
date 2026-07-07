/**
 * ProtectedSubjectFormDialog — GM declares a StoryProtectedSubject for the
 * selected story (#2001 Task 8).
 *
 * Mirrors TreasuredSubjectFormDialog's create-only shape: kind + the matching
 * typed reference (SubjectRefFields) + GM-only notes. No beat-level scoping
 * in this dialog — the model supports it (`beat` field, story-level when
 * null) but the brief's UI scope is story-level declarations only; beat
 * refinement stays a backend/telnet-only capability for now.
 */

import { useState } from 'react';
import { toast } from 'sonner';
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
import { useCreateProtectedSubject } from '../queries';
import type { ProtectedSubject } from '../types';
import { emptySubjectRef, SubjectRefFields, type SubjectRefValue } from './SubjectRefFields';

interface DRFFieldErrors {
  non_field_errors?: string[];
  story?: string[];
  detail?: string;
}

interface Props {
  storyId: number;
  onSuccess?: (subject: ProtectedSubject) => void;
}

export function ProtectedSubjectFormDialog({ storyId, onSuccess }: Props) {
  const [open, setOpen] = useState(false);
  const [ref, setRef] = useState<SubjectRefValue>(emptySubjectRef());
  const [notes, setNotes] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateProtectedSubject();

  function resetForm() {
    setRef(emptySubjectRef());
    setNotes('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') setFieldErrors(data as DRFFieldErrors);
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : 'An error occurred. Please try again.');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    createMutation.mutate(
      {
        story: storyId,
        subject_kind: ref.subject_kind,
        subject_sheet: ref.subject_sheet,
        subject_item: ref.subject_item,
        subject_society: ref.subject_society,
        subject_organization: ref.subject_organization,
        subject_label: ref.subject_label.trim(),
        notes: notes.trim(),
      },
      {
        onSuccess: (created) => {
          toast.success('Protected subject added');
          handleOpenChange(false);
          onSuccess?.(created);
        },
        onError: handleError,
      }
    );
  }

  const nonFieldErrors = [...(fieldErrors.non_field_errors ?? []), ...(fieldErrors.story ?? [])];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="add-protected-subject-btn">
          Add Protected Subject
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Protect a subject</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <SubjectRefFields value={ref} onChange={setRef} disabled={createMutation.isPending} />

          <div className="space-y-1">
            <Label htmlFor="protected-subject-notes">
              GM notes <span className="text-muted-foreground">(GM-only, optional)</span>
            </Label>
            <Textarea
              id="protected-subject-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Why is this critical to the story?"
              disabled={createMutation.isPending}
            />
          </div>

          {nonFieldErrors.length > 0 && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}
          {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Adding…' : 'Add'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
