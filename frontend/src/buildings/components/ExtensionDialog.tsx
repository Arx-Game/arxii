import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import type { RoomBuilderActionKey } from '../types';

interface ExtensionDialogProps {
  /** Any room in the building anchors the dispatch (the entry room). */
  anchorRoomId: number;
  currentBudget: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/** Open a BUILDING_EXTENSION project: grow the space budget via the contribution pipe. */
export function ExtensionDialog({
  anchorRoomId,
  currentBudget,
  open,
  onOpenChange,
  runAction,
}: ExtensionDialogProps) {
  const [addedBudget, setAddedBudget] = useState('');
  const added = Number(addedBudget);
  const valid = Number.isInteger(added) && added > 0;

  const submit = () => {
    runAction('start_building_extension', { room_id: anchorRoomId, added_budget: added });
    setAddedBudget('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Extend the building</DialogTitle>
          <DialogDescription>
            Opens a construction project; the space is added when the project completes and is
            funded through contributions. Current budget: {currentBudget} units.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="extension-budget">Units to add</Label>
          <Input
            id="extension-budget"
            type="number"
            min={1}
            value={addedBudget}
            onChange={(event) => setAddedBudget(event.target.value)}
            placeholder="50"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!valid}>
            Start extension project
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
