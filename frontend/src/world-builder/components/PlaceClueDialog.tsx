/**
 * PlaceClueDialog — place a RoomClue in the selected room (#2451).
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface PlaceClueDialogProps {
  roomId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keyed generically (not `WorldBuilderActionKey`) to match the story palette's own union (#2450). */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function PlaceClueDialog({ roomId, open, onOpenChange, runAction }: PlaceClueDialogProps) {
  const [clueSlug, setClueSlug] = useState('');
  const [detectDifficulty, setDetectDifficulty] = useState('0');

  useEffect(() => {
    if (open) {
      setClueSlug('');
      setDetectDifficulty('0');
    }
  }, [open]);

  const canSubmit = clueSlug.trim() !== '';

  const submit = () => {
    runAction('staff_place_clue', {
      room_id: roomId,
      clue_slug: clueSlug.trim(),
      detect_difficulty: Number(detectDifficulty) || 0,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Place clue</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="place-clue-slug">Clue slug</Label>
            <Input
              id="place-clue-slug"
              value={clueSlug}
              onChange={(event) => setClueSlug(event.target.value)}
              placeholder="torn-letter"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="place-clue-difficulty">Detect difficulty</Label>
            <Input
              id="place-clue-difficulty"
              type="number"
              value={detectDifficulty}
              onChange={(event) => setDetectDifficulty(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="place-clue-submit">
            Place
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
