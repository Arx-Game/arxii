import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useReauthGuard, useRecoveryCodes, useRegenerateRecoveryCodes } from '../hooks';
import { ReauthDialog } from './ReauthDialog';

interface RecoveryCodesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Shows the current unused recovery codes, with a guarded regenerate that replaces them. */
export function RecoveryCodesDialog({ open, onOpenChange }: RecoveryCodesDialogProps) {
  const { data, isLoading } = useRecoveryCodes(open);
  const regenerate = useRegenerateRecoveryCodes();
  const { run, dialogProps } = useReauthGuard();
  const [codes, setCodes] = useState<string[] | null>(null);

  useEffect(() => {
    if (data) setCodes(data.unused_codes);
  }, [data]);

  const copyAll = () => {
    void navigator.clipboard.writeText((codes ?? []).join('\n'));
  };

  const regenerateCodes = () =>
    run(() => regenerate.mutateAsync())
      .then((result) => {
        setCodes(result.unused_codes);
        toast.success('New recovery codes generated. The old ones no longer work.');
      })
      .catch((err: Error) => toast.error(err.message));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Recovery codes</DialogTitle>
          <DialogDescription>
            Each code works once. Keep them somewhere safe; they are the way back in if you lose
            your device.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <ol className="grid grid-cols-2 gap-1 rounded-lg border p-3 font-mono text-sm">
            {(codes ?? []).map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ol>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={copyAll}>
            Copy all
          </Button>
          <Button type="button" disabled={regenerate.isPending} onClick={regenerateCodes}>
            Regenerate
          </Button>
        </div>
        <ReauthDialog {...dialogProps} />
      </DialogContent>
    </Dialog>
  );
}
