import { useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SubmitButton } from '@/components/SubmitButton';
import type { AccountInvite, AccountInviteStatus } from '@/staff/types';
import {
  useAccountInviteList,
  useFetchVerificationLink,
  useIssueAccountInvite,
  useResendAccountInvite,
  useRevokeAccountInvite,
} from '@/staff/queries';

const STATUS_OPTIONS: { label: string; value: AccountInviteStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Pending', value: 'pending' },
  { label: 'Redeemed', value: 'redeemed' },
  { label: 'Revoked', value: 'revoked' },
  { label: 'Expired', value: 'expired' },
];

function statusVariant(
  status: AccountInviteStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'pending':
      return 'default';
    case 'redeemed':
      return 'secondary';
    case 'revoked':
    case 'expired':
      return 'destructive';
    default:
      return 'outline';
  }
}

function inviteLink(token: string): string {
  return `${window.location.origin}/register?invite=${token}`;
}

function IssueInviteForm() {
  const [email, setEmail] = useState('');
  const [note, setNote] = useState('');
  const mutation = useIssueAccountInvite();

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    mutation.mutate(
      { email, note },
      {
        onSuccess: (invite) => {
          toast.success(`Invite issued for ${invite.email}.`);
          setEmail('');
          setNote('');
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to issue invite.');
        },
      }
    );
  };

  return (
    <Card className="mb-6">
      <CardContent className="py-4">
        <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              placeholder="invitee@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="invite-note">Note (optional)</Label>
            <Input
              id="invite-note"
              placeholder="Why they're invited"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <SubmitButton isLoading={mutation.isPending} disabled={!email}>
            Issue Invite
          </SubmitButton>
        </form>
      </CardContent>
    </Card>
  );
}

/** Fallback when mail cannot reach a registered player (#3193): staff enter the
 * account's email and get its verification link to hand over directly, the same
 * trust model as Copy Link on an invite. */
function VerificationLinkForm() {
  const [email, setEmail] = useState('');
  const [link, setLink] = useState<string | null>(null);
  const mutation = useFetchVerificationLink();

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setLink(null);
    mutation.mutate(email, {
      onSuccess: (data) => {
        setLink(data.link);
        navigator.clipboard?.writeText(data.link);
        toast.success('Verification link copied.');
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : 'Failed to generate link.');
      },
    });
  };

  return (
    <Card className="mb-6">
      <CardContent className="py-4">
        <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="verification-email">Verification link for an account</Label>
            <Input
              id="verification-email"
              type="email"
              placeholder="player@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <SubmitButton isLoading={mutation.isPending} disabled={!email}>
            Copy Verification Link
          </SubmitButton>
        </form>
        {link && <p className="mt-3 break-all text-sm text-muted-foreground">{link}</p>}
      </CardContent>
    </Card>
  );
}

function InviteRow({ invite }: { invite: AccountInvite }) {
  const revoke = useRevokeAccountInvite();
  const resend = useResendAccountInvite();

  const handleCopyLink = () => {
    navigator.clipboard?.writeText(inviteLink(invite.token));
    toast.success('Invite link copied.');
  };

  const handleResend = () => {
    resend.mutate(invite.id, {
      onSuccess: () => toast.success(`Invite re-sent to ${invite.email}.`),
      onError: (err) =>
        toast.error(err instanceof Error ? err.message : 'Failed to resend invite.'),
    });
  };

  const handleRevoke = () => {
    revoke.mutate(invite.id, {
      onSuccess: () => toast.success(`Invite for ${invite.email} revoked.`),
      onError: () => toast.error('Failed to revoke invite.'),
    });
  };

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-4 py-4">
        <div>
          <p className="font-medium">{invite.email}</p>
          <p className="text-sm text-muted-foreground">
            Invited by {invite.invited_by_username} &middot;{' '}
            {new Date(invite.created_at).toLocaleDateString()}
            {invite.note && <> &middot; {invite.note}</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusVariant(invite.status)}>{invite.status}</Badge>
          {invite.status === 'pending' && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleResend}
                disabled={resend.isPending}
              >
                Resend Email
              </Button>
              <Button variant="outline" size="sm" onClick={handleCopyLink}>
                Copy Link
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRevoke}
                disabled={revoke.isPending}
              >
                Revoke
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function StaffInvitesPage() {
  const [statusFilter, setStatusFilter] = useState<AccountInviteStatus | undefined>(undefined);
  const { data, isLoading } = useAccountInviteList(statusFilter);
  const invites = data?.results;

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Account Invites</h1>

      <IssueInviteForm />
      <VerificationLinkForm />

      <div className="mb-6 flex flex-wrap gap-2">
        {STATUS_OPTIONS.map((opt) => (
          <Button
            key={opt.label}
            variant={statusFilter === opt.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !invites?.length ? (
        <p className="text-muted-foreground">No invites found.</p>
      ) : (
        <div className="space-y-3">
          {invites.map((invite) => (
            <InviteRow key={invite.id} invite={invite} />
          ))}
        </div>
      )}
    </div>
  );
}
