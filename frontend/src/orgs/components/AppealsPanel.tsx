/**
 * AppealsPanel (#3293) — the member view of appeals to organizations.
 *
 * Mounted on the members-only `OrgPage`: any member (any rank) reads the
 * org's open and resolved appeals, signs onto an open one to show support,
 * and — if their rank carries `can_resolve_appeals` (or they're staff) —
 * resolves it with a written answer. The backend enforces every permission
 * here; this panel shows the same actions to every member and lets a
 * non-privileged attempt surface as a toast error, mirroring how
 * `CrisisCard` (`OrgPage.tsx`) already handles a judgment-call attempt.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import {
  useOrgAppealsQuery,
  useResolveOrgAppealMutation,
  useSignonOrgAppealMutation,
  useWithdrawOrgAppealMutation,
} from '@/orgs/queries';
import type { OrgAppeal } from '@/orgs/api';

const STATE_VARIANT: Record<OrgAppeal['state'], 'secondary' | 'default' | 'destructive'> = {
  open: 'secondary',
  granted: 'default',
  declined: 'destructive',
  withdrawn: 'destructive',
};

const STATE_LABEL: Record<OrgAppeal['state'], string> = {
  open: 'Open',
  granted: 'Granted',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
};

function SignonDialog({ orgId, appeal }: { orgId: number; appeal: OrgAppeal }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const signon = useSignonOrgAppealMutation(orgId);

  function handleSubmit() {
    signon.mutate(
      { appealId: appeal.id, note: note.trim() },
      {
        onSuccess: () => {
          toast.success('You sign onto the appeal.');
          setOpen(false);
          setNote('');
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not sign onto the appeal.'),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" data-testid="appeal-signon-trigger">
          Sign On
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sign onto &ldquo;{appeal.title}&rdquo;</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="appeal-signon-note">Note (optional)</Label>
          <Input
            id="appeal-signon-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="I'll ride with them."
          />
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={signon.isPending}>
            Sign On
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResolveDialog({ orgId, appeal }: { orgId: number; appeal: OrgAppeal }) {
  const [open, setOpen] = useState(false);
  const [verdict, setVerdict] = useState<'grant' | 'decline'>('grant');
  const [answer, setAnswer] = useState('');
  const resolve = useResolveOrgAppealMutation(orgId);

  function handleSubmit() {
    resolve.mutate(
      { appealId: appeal.id, verdict, answer: answer.trim() },
      {
        onSuccess: () => {
          toast.success(verdict === 'grant' ? 'Appeal granted.' : 'Appeal declined.');
          setOpen(false);
          setAnswer('');
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not resolve the appeal.'),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="appeal-resolve-trigger">
          Resolve
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve &ldquo;{appeal.title}&rdquo;</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <RadioGroup
            value={verdict}
            onValueChange={(val) => setVerdict(val as 'grant' | 'decline')}
            className="flex flex-col gap-2"
          >
            <label className="flex items-center gap-2">
              <RadioGroupItem value="grant" id="appeal-verdict-grant" />
              <span>Grant</span>
            </label>
            <label className="flex items-center gap-2">
              <RadioGroupItem value="decline" id="appeal-verdict-decline" />
              <span>Decline</span>
            </label>
          </RadioGroup>
          <div className="space-y-2">
            <Label htmlFor="appeal-answer">Written answer</Label>
            <Textarea
              id="appeal-answer"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Guards are dispatched to the road at dawn."
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={resolve.isPending}>
            {verdict === 'grant' ? 'Grant' : 'Decline'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AppealRow({ orgId, appeal }: { orgId: number; appeal: OrgAppeal }) {
  const withdraw = useWithdrawOrgAppealMutation(orgId);

  function handleWithdraw() {
    withdraw.mutate(appeal.id, {
      onSuccess: () => toast.success('Appeal withdrawn.'),
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : 'Could not withdraw the appeal.'),
    });
  }

  return (
    <li className="rounded-md border p-3" data-testid="appeal-row">
      <div className="flex items-center gap-2">
        <Badge variant={STATE_VARIANT[appeal.state]}>{STATE_LABEL[appeal.state]}</Badge>
        <span className="font-semibold">{appeal.title}</span>
        <span className="text-sm text-muted-foreground">from {appeal.petitioner_persona_name}</span>
      </div>
      <p className="mt-1 text-sm">{appeal.body}</p>
      {appeal.signons.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          Signed on: {appeal.signons.map((s) => s.member_persona_name).join(', ')}
        </p>
      )}
      {appeal.state !== 'open' && appeal.resolution_text && (
        <p className="mt-2 text-sm italic">
          &ldquo;{appeal.resolution_text}&rdquo;
          {appeal.resolved_by_persona_name && <> — {appeal.resolved_by_persona_name}</>}
        </p>
      )}
      {appeal.state === 'open' && (
        <div className="mt-2 flex flex-wrap gap-2">
          <SignonDialog orgId={orgId} appeal={appeal} />
          <ResolveDialog orgId={orgId} appeal={appeal} />
          <Button
            size="sm"
            variant="ghost"
            disabled={withdraw.isPending}
            onClick={handleWithdraw}
            data-testid="appeal-withdraw-trigger"
          >
            Withdraw
          </Button>
        </div>
      )}
    </li>
  );
}

export function AppealsPanel({ orgId }: { orgId: number }) {
  const { data: appeals = [], isLoading } = useOrgAppealsQuery(orgId);

  return (
    <Card data-testid="appeals-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Appeals</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : appeals.length === 0 ? (
          <p className="text-sm text-muted-foreground">No appeals have been lodged.</p>
        ) : (
          <ul className="space-y-2">
            {appeals.map((appeal) => (
              <AppealRow key={appeal.id} orgId={orgId} appeal={appeal} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
