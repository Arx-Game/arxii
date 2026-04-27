/**
 * SendGemitDialog — Staff-only broadcast gemit composer.
 *
 * Sends POST /api/narrative/gemits/ with a body and optional era / story links.
 * Mounted on the StaffWorkloadPage via a "Broadcast Gemit" button.
 *
 * The dialog renders optimistically — if the caller is not staff, the API
 * returns 403 which surfaces as a toast without crashing the page.
 *
 * Era and story are typed by ID (number) rather than full autocomplete to keep
 * this component self-contained. Staff know the IDs from the workload page
 * context (era IDs are visible in the EraAdminPage). A future wave can upgrade
 * to autocomplete selectors.
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useBroadcastGemit } from '../queries';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  body?: string[];
  related_era?: string[];
  related_story?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SendGemitDialog() {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState('');
  const [relatedEraRaw, setRelatedEraRaw] = useState('');
  const [relatedStoryRaw, setRelatedStoryRaw] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const broadcastMutation = useBroadcastGemit();

  function resetForm() {
    setBody('');
    setRelatedEraRaw('');
    setRelatedStoryRaw('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function parseOptionalId(raw: string): number | null | undefined {
    const trimmed = raw.trim();
    if (!trimmed) return undefined;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const trimmedBody = body.trim();
    if (!trimmedBody) {
      setFieldErrors({ body: ['Gemit body is required.'] });
      return;
    }

    const relatedEra = parseOptionalId(relatedEraRaw);
    const relatedStory = parseOptionalId(relatedStoryRaw);

    broadcastMutation.mutate(
      {
        body: trimmedBody,
        related_era: relatedEra ?? null,
        related_story: relatedStory ?? null,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Gemit broadcast — all online accounts notified');
        },
        onError: (err: unknown) => {
          const fetchErr = err as { status?: number; response?: Response };
          if (fetchErr.status === 403) {
            toast.error('Permission denied. Only staff can broadcast gemits.');
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
                toast.error('Failed to broadcast gemit. Please try again.');
              });
            return;
          }
          const message =
            err instanceof Error ? err.message : 'Failed to broadcast gemit. Please try again.';
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
        <Button variant="default" size="sm" data-testid="broadcast-gemit-button">
          Broadcast Gemit
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Broadcast Gemit</DialogTitle>
            <DialogDescription>
              Send a server-wide announcement to all online players in real time. Gemits are also
              persisted for players who are offline.
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
              <Label htmlFor="gemit-body">Message</Label>
              <Textarea
                id="gemit-body"
                placeholder="Write your server-wide announcement here…"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                data-testid="gemit-body-input"
              />
              {fieldErrors.body && fieldErrors.body.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.body.join(' ')}</p>
              )}
            </div>

            {/* Optional related era */}
            <div className="space-y-1.5">
              <Label htmlFor="gemit-era">
                Related era ID <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="gemit-era"
                type="number"
                min={1}
                placeholder="e.g. 3"
                value={relatedEraRaw}
                onChange={(e) => setRelatedEraRaw(e.target.value)}
                data-testid="gemit-era-input"
              />
              {fieldErrors.related_era && fieldErrors.related_era.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.related_era.join(' ')}</p>
              )}
            </div>

            {/* Optional related story */}
            <div className="space-y-1.5">
              <Label htmlFor="gemit-story">
                Related story ID <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="gemit-story"
                type="number"
                min={1}
                placeholder="e.g. 17"
                value={relatedStoryRaw}
                onChange={(e) => setRelatedStoryRaw(e.target.value)}
                data-testid="gemit-story-input"
              />
              {fieldErrors.related_story && fieldErrors.related_story.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.related_story.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={broadcastMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={broadcastMutation.isPending || !body.trim()}>
              {broadcastMutation.isPending ? 'Broadcasting…' : 'Broadcast'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
