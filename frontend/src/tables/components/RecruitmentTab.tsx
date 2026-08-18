/**
 * RecruitmentTab — invites + application queue for a GM table (#3268).
 *
 * Mounted only for GM/staff viewers (same gate as TableDetailPage's admin row).
 * Both `/api/gm/invites/` and `/api/gm/queue/` are scoped to the requesting
 * GM's account across ALL their tables (staff see everything), not to this
 * one table — there is no `table` filter on either endpoint (world/gm/views.py).
 *
 * Approve/Deny render only when `account.is_gm` (Decision 6): the queue
 * action endpoint requires a GMProfile (`IsGM` permission), so staff viewing
 * a table they don't personally GM would only get a 403 from those buttons.
 * They instead see read-only rows plus a pointer to the staff review page.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { toast } from 'sonner';
import type { RootState } from '@/store/store';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { MintInviteDialog } from './MintInviteDialog';
import { useActionGMApplication, useGMQueue, useInvites, useRevokeInvite } from '../queries';
import type { GMQueueApplication, GMRosterInvite, GMTable } from '../types';

// ---------------------------------------------------------------------------
// Callout — create a character for this table
// ---------------------------------------------------------------------------

function CreateCharacterCallout() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Create a character for this table</CardTitle>
        <CardDescription>
          Author a new roster character through the character creator, then mint an invite once
          it&rsquo;s ready. Character creation uses the same shared single-draft slot as any other
          character you create, so finish or discard an existing draft first.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild variant="outline" size="sm">
          <Link to="/characters/create">Create a character</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Invites section
// ---------------------------------------------------------------------------

function formatExpiry(expiresAt: string | null): string {
  if (!expiresAt) return 'No expiry';
  return new Date(expiresAt).toLocaleString();
}

function InviteRow({
  invite,
  onRevoke,
}: {
  invite: GMRosterInvite;
  onRevoke: (invite: GMRosterInvite) => void;
}) {
  function handleCopy() {
    navigator.clipboard?.writeText(invite.code);
    toast.success('Invite code copied.');
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-3">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-muted px-2 py-0.5 text-sm">{invite.code}</code>
          <Button type="button" variant="ghost" size="sm" onClick={handleCopy}>
            Copy
          </Button>
          <Badge variant={invite.is_public ? 'outline' : 'secondary'}>
            {invite.is_public ? 'Public' : 'Private'}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {formatExpiry(invite.expires_at)} &middot; Claimed by {invite.claimed_username ?? '-'}
        </p>
      </div>
      {!invite.claimed_at && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="text-destructive hover:bg-destructive/10"
          onClick={() => onRevoke(invite)}
        >
          Revoke
        </Button>
      )}
    </div>
  );
}

function RevokeInviteDialog({
  invite,
  open,
  onOpenChange,
}: {
  invite: GMRosterInvite | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const revokeMutation = useRevokeInvite();

  function handleConfirm() {
    if (!invite) return;
    revokeMutation.mutate(invite.id, {
      onSuccess: () => {
        toast.success('Invite revoked.');
        onOpenChange(false);
      },
      onError: () => {
        toast.error('Failed to revoke invite.');
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Revoke Invite</DialogTitle>
          <DialogDescription>
            Revoke invite <strong>{invite?.code}</strong>? This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={revokeMutation.isPending}
          >
            {revokeMutation.isPending ? 'Revoking…' : 'Revoke Invite'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InvitesSection() {
  const { data, isLoading } = useInvites();
  const [revokeTarget, setRevokeTarget] = useState<GMRosterInvite | null>(null);

  const invites = data?.results ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">Invites</CardTitle>
          <CardDescription>Claim codes for characters you oversee.</CardDescription>
        </div>
        <MintInviteDialog>
          <Button size="sm">Mint invite</Button>
        </MintInviteDialog>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : invites.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No invites minted yet.</p>
        ) : (
          <div className="divide-y">
            {invites.map((invite) => (
              <InviteRow key={invite.id} invite={invite} onRevoke={setRevokeTarget} />
            ))}
          </div>
        )}
      </CardContent>

      <RevokeInviteDialog
        invite={revokeTarget}
        open={revokeTarget !== null}
        onOpenChange={(next) => {
          if (!next) setRevokeTarget(null);
        }}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Application queue section
// ---------------------------------------------------------------------------

function QueueRow({ application, isGM }: { application: GMQueueApplication; isGM: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [denying, setDenying] = useState(false);
  const [denyNotes, setDenyNotes] = useState('');
  const actionMutation = useActionGMApplication();

  function handleApprove() {
    actionMutation.mutate(
      { id: application.id, action: 'approve' },
      {
        onSuccess: () => toast.success(`${application.character_key} approved.`),
        onError: () => toast.error('Failed to approve application.'),
      }
    );
  }

  function handleDenySubmit() {
    if (!denyNotes.trim()) return;
    actionMutation.mutate(
      { id: application.id, action: 'deny', reviewNotes: denyNotes.trim() },
      {
        onSuccess: () => {
          toast.success(`${application.character_key} denied.`);
          setDenying(false);
          setDenyNotes('');
        },
        onError: () => toast.error('Failed to deny application.'),
      }
    );
  }

  return (
    <div className="space-y-2 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{application.character_key}</p>
          <p className="text-xs text-muted-foreground">
            Applicant {application.applicant_username} &middot;{' '}
            {new Date(application.applied_date).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? 'Hide application' : 'View application'}
          </Button>
          {isGM && !denying && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleApprove}
                disabled={actionMutation.isPending}
              >
                Approve
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="text-destructive hover:bg-destructive/10"
                onClick={() => setDenying(true)}
                disabled={actionMutation.isPending}
              >
                Deny
              </Button>
            </>
          )}
        </div>
      </div>

      {expanded && (
        <p className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
          {application.application_text}
        </p>
      )}

      {isGM && denying && (
        <div className="space-y-2 rounded-md border p-3">
          <label className="text-sm font-medium" htmlFor={`deny-notes-${application.id}`}>
            Denial notes *
          </label>
          <Textarea
            id={`deny-notes-${application.id}`}
            value={denyNotes}
            onChange={(e) => setDenyNotes(e.target.value)}
            placeholder="Let the applicant know why this application was denied."
            rows={3}
            required
          />
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setDenying(false);
                setDenyNotes('');
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={handleDenySubmit}
              disabled={!denyNotes.trim() || actionMutation.isPending}
            >
              {actionMutation.isPending ? 'Denying…' : 'Confirm Deny'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function QueueSection({ isGM }: { isGM: boolean }) {
  const { data, isLoading } = useGMQueue();
  const applications = data?.results ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Application Queue</CardTitle>
        <CardDescription>Pending applications for characters you oversee.</CardDescription>
      </CardHeader>
      <CardContent>
        {!isGM && (
          <p className="mb-3 text-sm text-muted-foreground">
            You can view but not act on applications here.{' '}
            <Link to="/staff/roster-applications" className="underline">
              Review roster applications
            </Link>
            .
          </p>
        )}
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : applications.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No pending applications.</p>
        ) : (
          <div className="divide-y">
            {applications.map((application) => (
              <QueueRow key={application.id} application={application} isGM={isGM} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface RecruitmentTabProps {
  /**
   * Unused today: neither /api/gm/invites/ nor /api/gm/queue/ take a `table`
   * filter (both are GM-account-scoped, world/gm/views.py — see module docblock).
   * Kept for signature parity with the other table-detail tabs (TableBulletin,
   * TableStoryRoster, TableMemberRoster all take `{ table }`) and in case a
   * table-scoped filter is added later.
   */
  table: GMTable;
}

export function RecruitmentTab({ table: _table }: RecruitmentTabProps) {
  const isGM = useSelector((state: RootState) => state.auth.account?.is_gm ?? false);

  return (
    <div className="space-y-6">
      <CreateCharacterCallout />
      <InvitesSection />
      <QueueSection isGM={isGM} />
    </div>
  );
}
