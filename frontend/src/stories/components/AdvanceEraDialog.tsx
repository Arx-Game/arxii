/**
 * AdvanceEraDialog — confirm before advancing an UPCOMING era to ACTIVE.
 *
 * Staff-only action. The current ACTIVE era will be closed atomically.
 */

import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAdvanceEra } from '../queries';
import type { Era } from '../types';

interface AdvanceEraDialogProps {
  open: boolean;
  onClose: () => void;
  era: Era | null;
}

export function AdvanceEraDialog({ open, onClose, era }: AdvanceEraDialogProps) {
  const advanceEra = useAdvanceEra();

  async function handleConfirm() {
    if (!era) return;
    try {
      await advanceEra.mutateAsync(era.id);
      toast.success(`Season ${era.season_number} "${era.display_name}" is now the active era.`);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to advance era.');
    }
  }

  if (!era) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Advance to Season {era.season_number}?</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          Advancing to <span className="font-medium text-foreground">{era.display_name}</span> will
          close the current active era. Stories continue across eras — no in-flight stories will be
          affected.
        </p>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={advanceEra.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={advanceEra.isPending}
            data-testid="advance-era-confirm"
          >
            {advanceEra.isPending ? 'Advancing…' : 'Advance Era'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
