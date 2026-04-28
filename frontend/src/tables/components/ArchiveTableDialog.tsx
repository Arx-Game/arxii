/**
 * ArchiveTableDialog — GM archives the whole table.
 *
 * Sets the table's status to ARCHIVED. Stories at this table will need to
 * be detached or reassigned separately.
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
import { useArchiveTable } from '../queries';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ArchiveTableDialogProps {
  tableId: number;
  tableName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ArchiveTableDialog({
  tableId,
  tableName,
  open,
  onOpenChange,
}: ArchiveTableDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const archiveMutation = useArchiveTable();

  function handleConfirm() {
    setError(null);
    archiveMutation.mutate(tableId, {
      onSuccess: () => {
        toast.success(`${tableName} archived`);
        onOpenChange(false);
      },
      onError: () => {
        setError('Failed to archive table. Please try again.');
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Archive Table</DialogTitle>
          <DialogDescription>
            Archive <strong>{tableName}</strong>?
          </DialogDescription>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          This will set the table&rsquo;s status to ARCHIVED. Stories at this table will need to be
          detached or reassigned.
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
            disabled={archiveMutation.isPending}
          >
            {archiveMutation.isPending ? 'Archiving…' : 'Archive Table'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
