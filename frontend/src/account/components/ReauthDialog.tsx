import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { reauthenticateWithCode, reauthenticateWithPassword } from '../api';
import type { ReauthDialogProps } from '../hooks';

/** Asks for the password, or a 2FA code when the account has one, then retries the caller. */
export function ReauthDialog({ open, flows, onSuccess, onCancel }: ReauthDialogProps) {
  const useCode = flows.includes('mfa_reauthenticate') && !flows.includes('reauthenticate');
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (useCode) await reauthenticateWithCode(value);
      else await reauthenticateWithPassword(value);
      setValue('');
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Not accepted.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Confirm it is you</DialogTitle>
          <DialogDescription>
            {useCode
              ? 'Enter a code from your authenticator app to continue.'
              : 'Enter your password to continue. This is asked again after a few minutes.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Label htmlFor="reauth-value">{useCode ? 'Authenticator code' : 'Password'}</Label>
          <Input
            id="reauth-value"
            type={useCode ? 'text' : 'password'}
            inputMode={useCode ? 'numeric' : undefined}
            autoComplete={useCode ? 'one-time-code' : 'current-password'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={!value || busy}>
              Continue
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
