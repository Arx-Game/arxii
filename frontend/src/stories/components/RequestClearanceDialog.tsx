/**
 * RequestClearanceDialog — a GM requests custody clearance against another
 * story's protected subject via the identity path (#2001 Task 8):
 * subject_kind + one typed ref, no `protected_subject` pk required — this is
 * the only self-serviceable path for a GM who only knows the custodian's
 * username, never the protected_subject id (see CustodyVerdict /
 * CustodyClearanceRequestRequest's docstring). The server resolves the
 * identity to every active StoryProtectedSubject sharing it (a subject can be
 * independently protected by more than one story) and returns one
 * CustodyClearance row per match.
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useRequestClearance, useStoryList } from '../queries';
import type { CustodyScope } from '../types';
import { emptySubjectRef, SubjectRefFields, type SubjectRefValue } from './SubjectRefFields';

const SCOPE_LABELS: Record<CustodyScope, string> = {
  appear: 'Appear (bring the subject on-screen)',
  harm: 'Harm (threaten or damage the subject)',
  remove: 'Remove (kill / destroy / permanently take the subject)',
};

interface DRFFieldErrors {
  detail?: string;
  non_field_errors?: string[];
  scope?: string[];
}

function numOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function RequestClearanceDialog() {
  const [open, setOpen] = useState(false);
  const [ref, setRef] = useState<SubjectRefValue>(emptySubjectRef());
  const [scope, setScope] = useState<CustodyScope>('appear');
  const [requestingStory, setRequestingStory] = useState('');
  const [requestingBeat, setRequestingBeat] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const requestMutation = useRequestClearance();
  // "My stories" — same scoping StoryAuthorPage uses (owner/lead-GM, or all for staff).
  const { data: myStories } = useStoryList({ page_size: 100 });

  function resetForm() {
    setRef(emptySubjectRef());
    setScope('appear');
    setRequestingStory('');
    setRequestingBeat('');
    setMessage('');
    setError('');
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    requestMutation.mutate(
      {
        subject_kind: ref.subject_kind,
        subject_sheet: ref.subject_sheet,
        subject_item: ref.subject_item,
        subject_society: ref.subject_society,
        subject_organization: ref.subject_organization,
        subject_label: ref.subject_label.trim(),
        scope,
        requesting_story: numOrNull(requestingStory),
        requesting_beat: numOrNull(requestingBeat),
        message: message.trim(),
      },
      {
        onSuccess: (created) => {
          toast.success(
            created.length === 1
              ? 'Clearance requested'
              : `Clearance requested (${created.length} protections matched)`
          );
          handleOpenChange(false);
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object' && 'response' in err) {
            const response = (err as { response?: Response }).response;
            if (response) {
              void response
                .json()
                .then((data: unknown) => {
                  const drf = data as DRFFieldErrors;
                  setError(
                    drf.detail ??
                      drf.non_field_errors?.join(' ') ??
                      drf.scope?.join(' ') ??
                      'Failed to request clearance.'
                  );
                })
                .catch(() => setError('Failed to request clearance.'));
              return;
            }
          }
          setError(err instanceof Error ? err.message : 'Failed to request clearance.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="request-clearance-btn">
          Request Clearance
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request custody clearance</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <SubjectRefFields value={ref} onChange={setRef} disabled={requestMutation.isPending} />

          <div className="space-y-1">
            <Label htmlFor="clearance-scope">What do you need to do</Label>
            <Select
              value={scope}
              onValueChange={(v) => setScope(v as CustodyScope)}
              disabled={requestMutation.isPending}
            >
              <SelectTrigger id="clearance-scope">
                <SelectValue placeholder="Scope" />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SCOPE_LABELS) as CustodyScope[]).map((s) => (
                  <SelectItem key={s} value={s}>
                    {SCOPE_LABELS[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="clearance-story">
              Your story <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Select
              value={requestingStory}
              onValueChange={setRequestingStory}
              disabled={requestMutation.isPending}
            >
              <SelectTrigger id="clearance-story">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                {(myStories?.results ?? []).map((story) => (
                  <SelectItem key={story.id} value={String(story.id)}>
                    {story.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="clearance-beat">
              Your beat id <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="clearance-beat"
              inputMode="numeric"
              value={requestingBeat}
              onChange={(e) => setRequestingBeat(e.target.value)}
              placeholder="e.g. 12"
              disabled={requestMutation.isPending}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="clearance-message">
              Message <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="clearance-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Why do you need this?"
              disabled={requestMutation.isPending}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={requestMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={requestMutation.isPending}>
              {requestMutation.isPending ? 'Requesting…' : 'Request'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
