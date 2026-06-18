import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type { IssueDraft } from '@/staff/types';

interface FileGithubIssueDialogProps {
  issueUrl: string;
  issueNumber: number | null;
  draft: IssueDraft;
  isPending: boolean;
  onSubmit: (title: string, body: string) => Promise<unknown>;
}

/** Staff-only control to file a public GitHub issue from a report (#1164).
 *
 *  Once filed, collapses to a "View issue #N" link. Before that, opens a dialog
 *  pre-filled with the server-redacted draft that staff edit and confirm — the
 *  "omit details" switch swaps in the minimal stub for sensitive / exploit bugs. */
export function FileGithubIssueDialog({
  issueUrl,
  issueNumber,
  draft,
  isPending,
  onSubmit,
}: FileGithubIssueDialogProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [omitDetails, setOmitDetails] = useState(false);

  if (issueUrl) {
    return (
      <Button variant="outline" asChild>
        <a href={issueUrl} target="_blank" rel="noreferrer">
          View issue{issueNumber ? ` #${issueNumber}` : ''}
        </a>
      </Button>
    );
  }

  function toggleOmitDetails(next: boolean) {
    setOmitDetails(next);
    setBody(next ? draft.stub_body : draft.body);
  }

  async function handleConfirm() {
    try {
      await onSubmit(title, body);
      toast.success('GitHub issue filed.');
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to file GitHub issue.');
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">File GitHub issue</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>File GitHub issue</DialogTitle>
          <DialogDescription>
            Review and edit before filing — this creates a public issue. Names we hold have been
            stripped; remove any remaining names or specifics yourself.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="issue-title">Title</Label>
            <Input
              id="issue-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={256}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="issue-body">Body</Label>
            <Textarea
              id="issue-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={12}
              className="font-mono text-xs"
            />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="omit-details" checked={omitDetails} onCheckedChange={toggleOmitDetails} />
            <Label htmlFor="omit-details" className="font-normal">
              Sensitive / exploit — omit details (file a minimal stub)
            </Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={isPending || !title.trim() || !body.trim()}>
            {isPending ? 'Filing…' : 'File issue'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
