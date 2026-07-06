/**
 * GiveItemDialog — modal opened from ItemDetailPanel's Give button (#1909).
 *
 * The `give` action needs a `recipient` (an ObjectDB pk resolved via the
 * websocket dispatcher's `recipient_id` kwarg) — a co-located character.
 * There's no generic target-picker in this codebase yet, so this is a
 * minimal select fed by the room-presence data the game rail already has
 * (`state.game.sessions[character].room.characters`), not a reusable
 * framework.
 */

import { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RoomStateObject } from '@/hooks/types';
import { dbrefToId } from '@/lib/dbref';

interface GiveItemDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Co-located characters (self already excluded by room state). */
  recipients: RoomStateObject[];
  onConfirm: (recipientId: number) => void;
}

export function GiveItemDialog({ open, onOpenChange, recipients, onConfirm }: GiveItemDialogProps) {
  const [recipientDbref, setRecipientDbref] = useState<string>(recipients[0]?.dbref ?? '');

  useEffect(() => {
    if (open) {
      setRecipientDbref(recipients[0]?.dbref ?? '');
    }
  }, [open, recipients]);

  const hasNoRecipients = recipients.length === 0;

  function handleConfirm() {
    if (!recipientDbref) return;
    const id = dbrefToId(recipientDbref);
    if (id === 0) return;
    onConfirm(id);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Give item</DialogTitle>
          <DialogDescription>Choose who to hand this to.</DialogDescription>
        </DialogHeader>

        {hasNoRecipients ? (
          <div className="flex flex-col items-center justify-center gap-3 px-4 py-8 text-center">
            <Users className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">Nobody else is here to give this to.</p>
          </div>
        ) : (
          <Select value={recipientDbref} onValueChange={setRecipientDbref}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a recipient…" />
            </SelectTrigger>
            <SelectContent>
              {recipients.map((character) => (
                <SelectItem key={character.dbref} value={character.dbref}>
                  {character.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <DialogFooter className="mt-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={hasNoRecipients}>
            Give
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
