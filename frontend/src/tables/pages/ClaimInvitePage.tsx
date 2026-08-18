/**
 * ClaimInvitePage — /invites/claim (#3268)
 *
 * A player follows a GM-minted invite link (`/invites/claim?code=...`) to
 * apply for the invited character. Claiming creates (or reuses an existing
 * pending) RosterApplication; the actual approve/deny still runs through the
 * normal GM queue (`RecruitmentTab`) — this page only submits the code.
 *
 * `GMInviteClaimView`'s response is just `{application_id}` — the claimed
 * roster entry/character aren't echoed back, so the success panel links
 * somewhere generic (the roster) rather than the specific entry.
 */

import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { bulletinErrorsFrom, type BulletinFieldErrors } from '../bulletinErrors';
import { FieldError, FormErrors } from '../components/FieldError';
import { useClaimInvite } from '../queries';

export function ClaimInvitePage() {
  const [searchParams] = useSearchParams();
  const [code, setCode] = useState(searchParams.get('code') ?? '');
  const [fieldErrors, setFieldErrors] = useState<BulletinFieldErrors>({});
  const [applicationId, setApplicationId] = useState<number | null>(null);

  const claimInvite = useClaimInvite();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    claimInvite.mutate(code.trim(), {
      onSuccess: (data) => setApplicationId(data.application_id),
      onError: (err: unknown) => setFieldErrors(bulletinErrorsFrom(err)),
    });
  }

  return (
    <div className="mx-auto max-w-md space-y-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>Claim Your Invite</CardTitle>
          <CardDescription>
            Enter the invite code a GM shared with you to apply for that character.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {applicationId !== null ? (
            <div className="space-y-4">
              <p className="text-sm">
                Application submitted. The table&apos;s GM will review it from their queue.
              </p>
              <Button asChild>
                <Link to="/roster">Browse the Roster</Link>
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="invite-code">Invite Code</Label>
                <Input
                  id="invite-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="e.g. sunny-day-1"
                  required
                  aria-describedby={fieldErrors.code ? 'invite-code-error' : undefined}
                />
                <FieldError errors={fieldErrors} field="code" id="invite-code-error" />
              </div>

              <FormErrors errors={fieldErrors} />

              <Button type="submit" disabled={code.trim().length === 0 || claimInvite.isPending}>
                {claimInvite.isPending ? 'Claiming…' : 'Claim Invite'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
