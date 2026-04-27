/**
 * LeaveTableDialog — player confirms leaving the table.
 *
 * Mirror of RemoveFromTableDialog but framed from the player's perspective.
 * Personal stories at this table are auto-detached on leave.
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
import { useLeaveTable } from '../queries';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LeaveTableDialogProps {
  tableId: number;
  tableName: string;
  membershipId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LeaveTableDialog({
  tableId,
  tableName,
  membershipId,
  open,
  onOpenChange,
}: LeaveTableDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const leaveMutation = useLeaveTable();

  function handleConfirm() {
    setError(null);
    leaveMutation.mutate(
      { membershipId, tableId },
      {
        onSuccess: () => {
          toast.success(`You have left ${tableName}`);
          onOpenChange(false);
        },
        onError: () => {
          setError('Failed to leave table. Please try again.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Leave Table</DialogTitle>
          <DialogDescription>
            Leave <strong>{tableName}</strong>?
          </DialogDescription>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          Your personal stories at this table will be detached and enter &ldquo;seeking GM&rdquo;
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
            disabled={leaveMutation.isPending}
          >
            {leaveMutation.isPending ? 'Leaving…' : 'Leave Table'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
