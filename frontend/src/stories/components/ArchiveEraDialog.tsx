/**
 * ArchiveEraDialog — confirm before archiving (concluding) an ACTIVE era.
 *
 * Staff-only action. Does not activate any new era.
 * Idempotent for already-CONCLUDED eras (safe to call again).
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
import { useArchiveEra } from '../queries';
import type { Era } from '../types';

interface ArchiveEraDialogProps {
  open: boolean;
  onClose: () => void;
  era: Era | null;
}

export function ArchiveEraDialog({ open, onClose, era }: ArchiveEraDialogProps) {
  const archiveEra = useArchiveEra();

  async function handleConfirm() {
    if (!era) return;
    try {
      await archiveEra.mutateAsync(era.id);
      toast.success(`Era "${era.display_name}" has been archived (concluded).`);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to archive era.');
    }
  }

  if (!era) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Archive Era?</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          Archive{' '}
          <span className="font-medium text-foreground">
            Season {era.season_number} — {era.display_name}
          </span>
          ? It will be marked <span className="font-medium">Concluded</span> without activating any
          new era. This action is safe to repeat.
        </p>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={archiveEra.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={archiveEra.isPending}
            data-testid="archive-era-confirm"
          >
            {archiveEra.isPending ? 'Archiving…' : 'Archive Era'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
