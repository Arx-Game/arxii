/**
 * LodgeAppealDialog (#3293) — the outsider "Appeal to <org>" surface.
 *
 * Mounted on `DossierPage` — the org's public page (readable by any
 * authenticated player, unlike the members-only `OrgPage`) — since lodging
 * an appeal needs no prior standing with the organization at all.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useLodgeOrgAppealMutation } from '@/orgs/queries';

export function LodgeAppealDialog({ orgId, orgName }: { orgId: number; orgName: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const lodge = useLodgeOrgAppealMutation(orgId);

  const canSubmit = title.trim() !== '' && body.trim() !== '' && !lodge.isPending;

  function reset() {
    setTitle('');
    setBody('');
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function handleSubmit() {
    if (!canSubmit) return;
    lodge.mutate(
      { title: title.trim(), body: body.trim() },
      {
        onSuccess: () => {
          toast.success(`Your appeal to ${orgName} has been lodged.`);
          handleOpenChange(false);
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not lodge the appeal.'),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button data-testid="appeal-to-org-trigger">Appeal to {orgName}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Appeal to {orgName}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="appeal-title">Title</Label>
            <Input
              id="appeal-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Aid against bandits on the road"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="appeal-body">Your appeal</Label>
            <Textarea
              id="appeal-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Our village has been raided twice this month..."
              rows={5}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!canSubmit} data-testid="appeal-submit">
            Lodge Appeal
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
