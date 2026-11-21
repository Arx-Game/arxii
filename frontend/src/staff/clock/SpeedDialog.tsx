import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { extractErrorMessage } from '@/lib/errors';

import { formatRatio } from './clockDate';
import { useSetClockSpeed } from './queries';
import type { ClockState } from './types';

interface SpeedDialogProps {
  clock: ClockState;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Change how fast the game's time runs. The date does not move when the speed does. */
export function SpeedDialog({ clock, open, onOpenChange }: SpeedDialogProps) {
  const [ratio, setRatio] = useState(formatRatio(clock.time_ratio));
  const [reason, setReason] = useState('');
  const mutation = useSetClockSpeed();
  const { reset } = mutation;

  useEffect(() => {
    if (open) {
      setRatio(formatRatio(clock.time_ratio));
      setReason('');
      reset();
    }
    // Read at the moment of opening only, like the date dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reset]);

  const value = Number.parseFloat(ratio);
  const ready = Number.isFinite(value) && value > 0 && reason.trim() !== '';

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    mutation.mutate(
      { ratio: value, reason: reason.trim() },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent {...NO_DESCRIPTION} className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Change speed</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="clock-ratio">Game days per real day</Label>
            <Input
              id="clock-ratio"
              type="number"
              min={0.01}
              step="any"
              value={ratio}
              onChange={(event) => setRatio(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="clock-speed-reason">Reason</Label>
            <Input
              id="clock-speed-reason"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          {mutation.error && (
            <p role="alert" className="text-sm text-destructive">
              {extractErrorMessage(mutation.error)}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || mutation.isPending}>
              Change speed
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
