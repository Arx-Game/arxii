import { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fetchTotpSetup } from '../api';
import { useActivateTotp, useRecoveryCodes, useReauthGuard } from '../hooks';
import { ReauthDialog } from './ReauthDialog';

interface TotpEnrolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEnrolled: () => void;
}

interface EnrolStepProps {
  setupError: string | null;
  setup: { secret: string; totp_url: string } | null;
  code: string;
  onCodeChange: (value: string) => void;
  error: string | null;
  onSubmit: (e: React.FormEvent) => void;
  submitting: boolean;
  onCopySecret: () => void;
}

/** The QR-and-code step. A separate function keeps the loading/error/ready states flat. */
function EnrolStep({
  setupError,
  setup,
  code,
  onCodeChange,
  error,
  onSubmit,
  submitting,
  onCopySecret,
}: EnrolStepProps) {
  if (setupError) return <p className="text-sm text-red-600">{setupError}</p>;
  if (!setup) return <p className="text-sm text-muted-foreground">Loading...</p>;
  return (
    <div className="space-y-3">
      <div className="flex justify-center">
        <QRCodeSVG value={setup.totp_url} size={192} />
      </div>
      <div className="flex items-center justify-between gap-2 rounded-lg border p-2">
        <code className="break-all text-xs">{setup.secret}</code>
        <Button type="button" size="sm" variant="outline" onClick={onCopySecret}>
          Copy
        </Button>
      </div>
      <form onSubmit={onSubmit} className="space-y-2">
        <Label htmlFor="totp-code">Authenticator code</Label>
        <Input
          id="totp-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => onCodeChange(e.target.value)}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={!code || submitting}>
          Turn on
        </Button>
      </form>
    </div>
  );
}

/** Enrolment: scan a QR code, confirm with a 6-digit code, then show recovery codes once. */
export function TotpEnrolDialog({ open, onOpenChange, onEnrolled }: TotpEnrolDialogProps) {
  const [setup, setSetup] = useState<{ secret: string; totp_url: string } | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<'enrol' | 'codes'>('enrol');
  const activate = useActivateTotp();
  const { run, dialogProps } = useReauthGuard();
  const recoveryCodes = useRecoveryCodes(stage === 'codes');

  useEffect(() => {
    if (!open) return;
    setStage('enrol');
    setCode('');
    setError(null);
    setSetup(null);
    setSetupError(null);
    fetchTotpSetup()
      .then(setSetup)
      .catch((err: Error) => setSetupError(err.message));
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await run(() => activate.mutateAsync(code));
      setStage('codes');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That code was not accepted.');
    }
  };

  const copySecret = () => {
    if (setup) void navigator.clipboard.writeText(setup.secret);
  };

  const copyAll = () => {
    void navigator.clipboard.writeText((recoveryCodes.data?.unused_codes ?? []).join('\n'));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        {stage === 'enrol' ? (
          <>
            <DialogHeader>
              <DialogTitle>Set up two-factor authentication</DialogTitle>
              <DialogDescription>
                Scan this with your authenticator app. Scan it with a second device too if you have
                one, so losing a phone does not lock you out.
              </DialogDescription>
            </DialogHeader>
            <EnrolStep
              setupError={setupError}
              setup={setup}
              code={code}
              onCodeChange={setCode}
              error={error}
              onSubmit={submit}
              submitting={activate.isPending}
              onCopySecret={copySecret}
            />
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Save these recovery codes</DialogTitle>
              <DialogDescription>
                Each code works once. Keep them somewhere safe; they are the way back in if you lose
                your device.
              </DialogDescription>
            </DialogHeader>
            <ol className="grid grid-cols-2 gap-1 rounded-lg border p-3 font-mono text-sm">
              {(recoveryCodes.data?.unused_codes ?? []).map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={copyAll}>
                Copy all
              </Button>
              <Button type="button" onClick={onEnrolled}>
                Done
              </Button>
            </div>
          </>
        )}
        <ReauthDialog {...dialogProps} />
      </DialogContent>
    </Dialog>
  );
}
