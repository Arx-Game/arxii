/**
 * PlaceClueDialog — place a RoomClue (active/search) or ClueTrigger
 * (passive/on-entry) in the selected room (#2451). A mode toggle switches
 * between the two placement kinds; they share the room + clue-slug fields,
 * only the active kind also carries a `detect_difficulty` (`ClueTrigger` has
 * no such field, see `world.clues.models.ClueTrigger`).
 *
 * "New clue…" (#3432) opens `AuthorClueDialog` alongside the slug field —
 * minting a clue is a separate SENIOR-GM/staff-gated dispatch
 * (`author_clue`), so on success this only pre-fills the slug field here;
 * placement itself still goes through the normal submit below.
 */
import { useEffect, useState } from 'react';

import { AuthorClueDialog } from '@/clues/components/AuthorClueDialog';
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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export interface PlaceClueDialogProps {
  roomId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keyed generically (not `WorldBuilderActionKey`) to match the story palette's own union (#2450). */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

type PlaceClueMode = 'active' | 'passive';

export function PlaceClueDialog({ roomId, open, onOpenChange, runAction }: PlaceClueDialogProps) {
  const [mode, setMode] = useState<PlaceClueMode>('active');
  const [clueSlug, setClueSlug] = useState('');
  const [detectDifficulty, setDetectDifficulty] = useState('0');

  useEffect(() => {
    if (open) {
      setMode('active');
      setClueSlug('');
      setDetectDifficulty('0');
    }
  }, [open]);

  const canSubmit = clueSlug.trim() !== '';
  const isPassive = mode === 'passive';

  const submit = () => {
    if (isPassive) {
      runAction('staff_place_clue_trigger', {
        room_id: roomId,
        clue_slug: clueSlug.trim(),
      });
    } else {
      runAction('staff_place_clue', {
        room_id: roomId,
        clue_slug: clueSlug.trim(),
        detect_difficulty: Number(detectDifficulty) || 0,
      });
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isPassive ? 'Place clue trigger' : 'Place clue'}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <Tabs value={mode} onValueChange={(value) => setMode(value as PlaceClueMode)}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="active">Search (active)</TabsTrigger>
              <TabsTrigger value="passive">On entry (passive)</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="place-clue-slug">Clue slug</Label>
              <AuthorClueDialog
                trigger={
                  <Button variant="link" size="sm" className="h-auto p-0">
                    New clue…
                  </Button>
                }
                onCreated={(slug) => setClueSlug(slug)}
              />
            </div>
            <Input
              id="place-clue-slug"
              value={clueSlug}
              onChange={(event) => setClueSlug(event.target.value)}
              placeholder="torn-letter"
            />
          </div>
          {!isPassive && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="place-clue-difficulty">Detect difficulty</Label>
              <Input
                id="place-clue-difficulty"
                type="number"
                value={detectDifficulty}
                onChange={(event) => setDetectDifficulty(event.target.value)}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="place-clue-submit">
            {isPassive ? 'Place trigger' : 'Place'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
