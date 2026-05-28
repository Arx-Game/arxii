/**
 * Modal dialog for editing a MissionTemplate's category set.
 *
 * Opened from MissionDetailPanel via a pencil button next to the
 * categories row. PATCHes {categories: number[]} to the template
 * endpoint; query invalidation refreshes the panel automatically.
 */

import { useState, useEffect } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { CategoryMultiSelect } from './CategoryMultiSelect';
import { usePatchMissionTemplate } from '../queries';

interface EditCategoriesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: number;
  initialCategories: readonly number[];
}

export function EditCategoriesDialog({
  open,
  onOpenChange,
  templateId,
  initialCategories,
}: EditCategoriesDialogProps) {
  const [value, setValue] = useState<number[]>([...initialCategories]);
  const patch = usePatchMissionTemplate();

  // Reset value to fresh initialCategories each time the dialog opens.
  // This ensures stale state from a previous open never bleeds into a new session.
  useEffect(() => {
    if (open) {
      setValue([...initialCategories]);
    }
  }, [open, initialCategories]);

  const onSave = async () => {
    try {
      await patch.mutateAsync({ id: templateId, body: { categories: value } });
      toast.success('Categories updated.');
      onOpenChange(false);
    } catch {
      toast.error('Failed to update categories.');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit categories</DialogTitle>
          <DialogDescription className="sr-only">
            Select categories for this template.
          </DialogDescription>
        </DialogHeader>
        <CategoryMultiSelect value={value} onChange={setValue} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={patch.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
