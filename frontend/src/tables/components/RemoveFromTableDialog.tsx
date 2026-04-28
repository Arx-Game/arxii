/**
 * RemoveFromTableDialog — GM confirms removing a member from the table.
 *
 * Soft-delete: the membership record remains with left_at set.
 * Personal stories at this table are auto-detached (enter 'seeking GM' state).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useRemoveMembership } from '../queries';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RemoveFromTableDialogProps {
  tableId: number;
  tableName: string;
  membershipId: number;
  personaName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RemoveFromTableDialog({
  tableId,
  tableName,
  membershipId,
  personaName,
  open,
  onOpenChange,
}: RemoveFromTableDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const removeMutation = useRemoveMembership();

  function handleConfirm() {
    setError(null);
    removeMutation.mutate(
      { membershipId, tableId },
      {
        onSuccess: () => {
          toast.success(`${personaName} removed from ${tableName}`);
          onOpenChange(false);
        },
        onError: () => {
          setError('Failed to remove member. Please try again.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Remove from Table</DialogTitle>
          <DialogDescription>
            Remove <strong>{personaName}</strong> from <strong>{tableName}</strong>?
          </DialogDescription>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          Their personal stories at this table will be detached and enter &ldquo;seeking GM&rdquo;
          state. Story history is preserved.
        </p>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={removeMutation.isPending}
          >
            {removeMutation.isPending ? 'Removing…' : 'Remove'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
