/**
 * HonorForm (#3466 Task 10) — write a paid, public honor journal for a deed.
 *
 * Only ever rendered when `can_honor.allowed` is true (the caller, `DeedPage`, gates on
 * that and shows the refusal reason instead when it's false) — but `can_honor.allowed`
 * is a point-in-time read, so the write can still be refused (another honorer spent the
 * last Hare, the deed hit its ceiling, etc. between the GET and this POST). That refusal
 * comes back as `400 {detail: <HonorRefused.user_message>}`, parsed into `ApiError.message`
 * by `honorDeed`/`readErrorDetail` — surfaced inline here, mirroring
 * `JournalComposerDialog`'s established inline-error convention (#3412 T4), since a toast
 * alone disappears before the player has necessarily read it.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { useHonorDeed } from '../queries';

interface Props {
  deedId: number;
  /** `can_honor.hares_required` — guaranteed non-null by the caller's allowed-gate. */
  hareCost: number;
  /** `can_honor.value_added` — the legend this honor will add, shown alongside the cost. */
  valueAdded: number;
}

export function HonorForm({ deedId, hareCost, valueAdded }: Props) {
  const [journalTitle, setJournalTitle] = useState('');
  const [journalBody, setJournalBody] = useState('');
  const honorDeed = useHonorDeed(deedId);

  function handleSubmit() {
    if (!journalTitle.trim() || !journalBody.trim() || honorDeed.isPending) return;
    honorDeed.mutate(
      { journal_title: journalTitle.trim(), journal_body: journalBody },
      {
        onSuccess: () => {
          toast.success('Honor recorded.');
          setJournalTitle('');
          setJournalBody('');
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to honor this deed');
        },
      }
    );
  }

  const canSubmit =
    journalTitle.trim().length > 0 && journalBody.trim().length > 0 && !honorDeed.isPending;
  const errorMessage =
    honorDeed.isError && honorDeed.error instanceof Error ? honorDeed.error.message : null;

  return (
    <div className="space-y-4" data-testid="honor-form">
      <p className="text-sm text-muted-foreground" data-testid="honor-form-cost">
        Honoring this deed costs <span className="font-medium">{hareCost}</span>{' '}
        {hareCost === 1 ? 'Golden Hare' : 'Golden Hares'} and adds{' '}
        <span className="font-medium">{valueAdded}</span> legend.
      </p>
      <div className="space-y-2">
        <Label htmlFor="honor-journal-title">Title</Label>
        <Input
          id="honor-journal-title"
          value={journalTitle}
          onChange={(e) => setJournalTitle(e.target.value)}
          placeholder="A title for this account"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="honor-journal-body">Account</Label>
        <Textarea
          id="honor-journal-body"
          value={journalBody}
          onChange={(e) => setJournalBody(e.target.value)}
          placeholder="Write what you witnessed…"
          className="min-h-[140px]"
        />
      </div>
      {errorMessage && (
        <div
          className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
          data-testid="honor-form-error"
        >
          <p>{errorMessage}</p>
        </div>
      )}
      <Button onClick={handleSubmit} disabled={!canSubmit}>
        {honorDeed.isPending ? 'Honoring…' : 'Honor This Deed'}
      </Button>
    </div>
  );
}
