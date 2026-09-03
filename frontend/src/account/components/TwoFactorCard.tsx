import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useAppSelector } from '@/store/hooks';
import {
  useAuthenticators,
  useDeactivateTotp,
  useReauthGuard,
  useSecuritySettings,
  useSetBlockTelnet,
} from '../hooks';
import { ReauthDialog } from './ReauthDialog';
import { RecoveryCodesDialog } from './RecoveryCodesDialog';
import { TotpEnrolDialog } from './TotpEnrolDialog';

export function TwoFactorCard() {
  const account = useAppSelector((s) => s.auth.account);
  const { data: authenticators = [], isLoading } = useAuthenticators();
  const { data: security } = useSecuritySettings();
  const setBlock = useSetBlockTelnet();
  const deactivate = useDeactivateTotp();
  const { run, dialogProps } = useReauthGuard();
  const [enrolOpen, setEnrolOpen] = useState(false);
  const [codesOpen, setCodesOpen] = useState(false);

  const enabled = authenticators.some((a) => a.type === 'totp');
  const recovery = authenticators.find((a) => a.type === 'recovery_codes');

  const turnOff = () =>
    run(() => deactivate.mutateAsync())
      .then(() => toast.success('Two-factor authentication is off.'))
      .catch((err: Error) => toast.error(err.message));

  let status: React.ReactNode;
  if (isLoading) {
    status = <p className="text-sm text-muted-foreground">Loading...</p>;
  } else if (enabled) {
    status = (
      <>
        <p className="text-sm">
          <strong>On.</strong>{' '}
          {recovery
            ? `${recovery.unused_code_count ?? 0} of ${recovery.total_code_count ?? 0} recovery codes unused.`
            : ''}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setCodesOpen(true)}>
            Recovery codes
          </Button>
          <Button variant="destructive" size="sm" disabled={deactivate.isPending} onClick={turnOff}>
            Turn off
          </Button>
        </div>
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="pr-4">
            <Label htmlFor="block-telnet">Refuse telnet sign-in while 2FA is on</Label>
            <p className="text-sm text-muted-foreground">
              Telnet sign-in still accepts your password alone, because telnet cannot ask for a
              code. Turn this on to refuse it and use the web client only.
            </p>
          </div>
          <Switch
            id="block-telnet"
            checked={security?.block_telnet_login_with_2fa ?? false}
            disabled={!security || setBlock.isPending}
            onCheckedChange={(next) =>
              setBlock.mutate(next, { onError: (err: Error) => toast.error(err.message) })
            }
            aria-label="Refuse telnet sign-in while 2FA is on"
          />
        </div>
      </>
    );
  } else if (account && !account.email_verified) {
    status = (
      <p className="text-sm text-muted-foreground">
        Verify your email address before turning this on.
      </p>
    );
  } else {
    status = (
      <>
        <p className="text-sm">
          <strong>Off.</strong> Telnet sign-in is not affected either way unless you choose to
          refuse it after turning this on.
        </p>
        <Button size="sm" onClick={() => setEnrolOpen(true)}>
          Set up
        </Button>
      </>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Two-factor authentication</CardTitle>
        <CardDescription>
          Optional. When on, signing in on the web asks for a code from your authenticator app after
          your password.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {status}
        <TotpEnrolDialog
          open={enrolOpen}
          onOpenChange={setEnrolOpen}
          onEnrolled={() => setEnrolOpen(false)}
        />
        <RecoveryCodesDialog open={codesOpen} onOpenChange={setCodesOpen} />
        <ReauthDialog {...dialogProps} />
      </CardContent>
    </Card>
  );
}
