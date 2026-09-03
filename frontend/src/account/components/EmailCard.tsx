import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  useCancelEmailChange,
  useEmailAddresses,
  useReauthGuard,
  useRequestEmailChange,
  useResendEmailChange,
} from '../hooks';
import type { EmailAddressInfo } from '../types';
import { ReauthDialog } from './ReauthDialog';

function CurrentAddress({
  isLoading,
  current,
}: {
  isLoading: boolean;
  current: EmailAddressInfo | undefined;
}) {
  if (isLoading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (!current) return <p className="text-sm text-muted-foreground">No email address on file.</p>;
  return (
    <div
      className="flex items-center justify-between rounded-lg border p-3"
      data-testid="current-email"
    >
      <span>{current.email}</span>
      <Badge variant={current.verified ? 'secondary' : 'destructive'}>
        {current.verified ? 'Verified' : 'Not verified'}
      </Badge>
    </div>
  );
}

export function EmailCard() {
  const { data: addresses = [], isLoading } = useEmailAddresses();
  const request = useRequestEmailChange();
  const resend = useResendEmailChange();
  const cancel = useCancelEmailChange();
  const { run, dialogProps } = useReauthGuard();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);

  const current = addresses.find((a) => a.primary) ?? addresses[0];
  const pending = addresses.find((a) => !a.primary && !a.verified);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await run(() => request.mutateAsync(email));
      toast.success(
        `Check ${email} for a verification link. Your current address stays active until then.`
      );
      setEmail('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the change.');
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email</CardTitle>
        <CardDescription>Where sign-in help and account notices are sent.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <CurrentAddress isLoading={isLoading} current={current} />
        {pending && (
          <div
            className="space-y-2 rounded-lg border border-dashed p-3"
            data-testid="pending-email"
          >
            <p className="text-sm">
              Pending change to <strong>{pending.email}</strong>. It takes effect once you open the
              link we sent there.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={resend.isPending}
                onClick={() =>
                  resend.mutate(pending.email, {
                    onSuccess: () => toast.success('Verification mail sent again.'),
                    onError: (err: Error) => toast.error(err.message),
                  })
                }
              >
                Resend
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={cancel.isPending}
                onClick={() =>
                  run(() => cancel.mutateAsync(pending.email)).catch((err: Error) =>
                    toast.error(err.message)
                  )
                }
              >
                Cancel change
              </Button>
            </div>
          </div>
        )}
        <form onSubmit={submit} className="space-y-2">
          <Label htmlFor="new-email">Change email</Label>
          <div className="flex gap-2">
            <Input
              id="new-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="new@address.example"
            />
            <Button type="submit" disabled={!email || request.isPending}>
              Send verification
            </Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
        <ReauthDialog {...dialogProps} />
      </CardContent>
    </Card>
  );
}
