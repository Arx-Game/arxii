/**
 * SendStoryOOCDialog — Lead GM / staff sends a story-scoped OOC notice.
 *
 * Rendered optimistically on the story detail page. If the caller does not
 * have Lead GM or staff permissions, the backend returns 403 which surfaces
 * as a toast — no client-side role check required.
 *
 * POST /api/stories/{id}/send-ooc/
 * Body: { body: string, ooc_note?: string }
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useSendStoryOOC } from '../queries';
import type { Story } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  body?: string[];
  ooc_note?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SendStoryOOCDialogProps {
  story: Story;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SendStoryOOCDialog({ story }: SendStoryOOCDialogProps) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState('');
  const [oocNote, setOocNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const sendMutation = useSendStoryOOC();

  function resetForm() {
    setBody('');
    setOocNote('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const trimmedBody = body.trim();
    if (!trimmedBody) {
      setFieldErrors({ body: ['Message body is required.'] });
      return;
    }

    sendMutation.mutate(
      {
        storyId: story.id,
        body: trimmedBody,
        ooc_note: oocNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('OOC notice sent to story participants');
        },
        onError: (err: unknown) => {
          const fetchErr = err as { status?: number; response?: Response };
          if (fetchErr.status === 403) {
            toast.error('Permission denied. Only Lead GMs and staff can send OOC notices.');
            setOpen(false);
            return;
          }
          if (fetchErr.response) {
            void fetchErr.response
              .json()
              .then((data: unknown) => {
                if (data && typeof data === 'object') {
                  setFieldErrors(data as DRFFieldErrors);
                }
              })
              .catch(() => {
                toast.error('Failed to send OOC notice. Please try again.');
              });
            return;
          }
          const message =
            err instanceof Error ? err.message : 'Failed to send OOC notice. Please try again.';
          toast.error(message);
        },
      }
    );
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="send-ooc-button">
          Send OOC notice
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Send OOC notice</DialogTitle>
            <DialogDescription>
              Send an out-of-character message to all participants in &ldquo;{story.title}&rdquo;.
            </DialogDescription>
          </DialogHeader>

          {/* Non-field / global error banner */}
          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Body */}
            <div className="space-y-1.5">
              <Label htmlFor="ooc-body">Message</Label>
              <Textarea
                id="ooc-body"
                placeholder="Write your OOC notice here…"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={5}
                maxLength={2000}
                data-testid="ooc-body-input"
              />
              {fieldErrors.body && fieldErrors.body.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.body.join(' ')}</p>
              )}
              <p className="text-right text-xs text-muted-foreground">{body.length} / 2000</p>
            </div>

            {/* OOC note */}
            <div className="space-y-1.5">
              <Label htmlFor="ooc-note">
                Internal OOC note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="ooc-note"
                placeholder="Visible only to staff and GMs with access to recipient characters…"
                value={oocNote}
                onChange={(e) => setOocNote(e.target.value)}
                rows={2}
                data-testid="ooc-note-input"
              />
              {fieldErrors.ooc_note && fieldErrors.ooc_note.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.ooc_note.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={sendMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={sendMutation.isPending || !body.trim()}>
              {sendMutation.isPending ? 'Sending…' : 'Send Notice'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
