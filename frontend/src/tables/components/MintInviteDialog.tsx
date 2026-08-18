/**
 * MintInviteDialog — GM mints a roster invite for a specific character (#3268).
 *
 * There is no existing search endpoint that scopes RosterEntry options to
 * "characters this GM oversees at this table" (fetchRosterEntries only filters
 * by roster/name/char_class/gender), so roster_entry is a plain numeric field —
 * the GM already knows which roster entry they're inviting for from the
 * table's story roster. The backend validates oversight server-side and
 * surfaces a field error if the GM does not oversee the given entry.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { bulletinErrorsFrom, type BulletinFieldErrors } from '../bulletinErrors';
import { FieldError, FormErrors } from './FieldError';
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
import { Switch } from '@/components/ui/switch';
import { useMintInvite } from '../queries';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MintInviteDialogProps {
  children: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MintInviteDialog({ children }: MintInviteDialogProps) {
  const [open, setOpen] = useState(false);
  const [rosterEntryId, setRosterEntryId] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [invitedEmail, setInvitedEmail] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [fieldErrors, setFieldErrors] = useState<BulletinFieldErrors>({});

  const mintMutation = useMintInvite();

  function resetForm() {
    setRosterEntryId('');
    setIsPublic(false);
    setInvitedEmail('');
    setExpiresAt('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  const parsedRosterEntryId = Number(rosterEntryId);
  const isValid = rosterEntryId.trim() !== '' && Number.isInteger(parsedRosterEntryId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;
    setFieldErrors({});

    mintMutation.mutate(
      {
        roster_entry: parsedRosterEntryId,
        is_public: isPublic,
        invited_email: invitedEmail.trim() || undefined,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
      },
      {
        onSuccess: (invite) => {
          toast.success(`Invite minted: ${invite.code}`);
          setOpen(false);
        },
        onError: (err: unknown) => {
          setFieldErrors(bulletinErrorsFrom(err));
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Mint Invite</DialogTitle>
          <DialogDescription>
            Generate a claim code for a roster character you oversee at this table.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => handleSubmit(e)} className="space-y-4">
          {/* Roster entry */}
          <div className="space-y-1">
            <Label htmlFor="invite-roster-entry">Roster entry ID *</Label>
            <Input
              id="invite-roster-entry"
              type="number"
              min={1}
              value={rosterEntryId}
              onChange={(e) => setRosterEntryId(e.target.value)}
              placeholder="e.g. 42"
              required
            />
            <FieldError errors={fieldErrors} field="roster_entry" />
          </div>

          {/* Public toggle */}
          <div className="flex items-center gap-3">
            <Switch id="invite-public" checked={isPublic} onCheckedChange={setIsPublic} />
            <Label htmlFor="invite-public">Public (anyone with the code can claim)</Label>
          </div>

          {/* Invited email (private invites) */}
          <div className="space-y-1">
            <Label htmlFor="invite-email">Invited email (optional)</Label>
            <Input
              id="invite-email"
              type="email"
              value={invitedEmail}
              onChange={(e) => setInvitedEmail(e.target.value)}
              placeholder="player@example.com"
              disabled={isPublic}
            />
            <FieldError errors={fieldErrors} field="invited_email" />
          </div>

          {/* Expiry */}
          <div className="space-y-1">
            <Label htmlFor="invite-expires">Expires (optional)</Label>
            <Input
              id="invite-expires"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
            />
            <FieldError errors={fieldErrors} field="expires_at" />
          </div>

          {/* Global errors */}
          <FormErrors errors={fieldErrors} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || mintMutation.isPending}>
              {mintMutation.isPending ? 'Minting…' : 'Mint Invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
