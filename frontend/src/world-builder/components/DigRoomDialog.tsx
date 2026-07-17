/**
 * DigRoomDialog — dig a new world room into an AUTHORED area (#2449).
 *
 * Design call (see task-6 report): rather than porting BuilderCanvas's
 * ghost-ring ("+" cells around every placed room, one dig direction each"),
 * this canvas's ghost cells (reused from `@/map-canvas`'s `ghostCells`) just
 * prefill `grid_x`/`grid_y` here — a plain "Dig room" toolbar button opens
 * the same dialog with the fields left blank for manual entry. One dialog,
 * two entry points; no separate direction concept (world rooms place by
 * absolute grid cell, not relative-to-anchor like the building dig flow).
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
import { Textarea } from '@/components/ui/textarea';

import type { WorldBuilderActionKey } from '../types';

export interface DigRoomDialogProps {
  areaId: number;
  floor: number;
  /** Prefills grid position from a ghost-cell click; absent for the plain "Dig room" button. */
  prefill?: { grid_x: number; grid_y: number };
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

export function DigRoomDialog({
  areaId,
  floor,
  prefill,
  open,
  onOpenChange,
  runAction,
}: DigRoomDialogProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [gridX, setGridX] = useState('');
  const [gridY, setGridY] = useState('');

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setGridX(prefill ? String(prefill.grid_x) : '');
      setGridY(prefill ? String(prefill.grid_y) : '');
    }
  }, [open, prefill]);

  const canSubmit = name.trim() !== '';

  const submit = () => {
    const kwargs: Record<string, unknown> = {
      area_id: areaId,
      name: name.trim(),
      floor,
    };
    if (description.trim()) kwargs.description = description.trim();
    if (gridX.trim() !== '' && gridY.trim() !== '') {
      kwargs.grid_x = Number(gridX);
      kwargs.grid_y = Number(gridY);
    }
    runAction('staff_dig_room', kwargs);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Dig world room</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-room-name">Room name</Label>
            <Input
              id="dig-room-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Market Square"
            />
          </div>
          <div className="flex gap-2">
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="dig-room-grid-x">Grid X</Label>
              <Input
                id="dig-room-grid-x"
                type="number"
                value={gridX}
                onChange={(event) => setGridX(event.target.value)}
                disabled={prefill != null}
              />
            </div>
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="dig-room-grid-y">Grid Y</Label>
              <Input
                id="dig-room-grid-y"
                type="number"
                value={gridY}
                onChange={(event) => setGridY(event.target.value)}
                disabled={prefill != null}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-room-description">Description (optional)</Label>
            <Textarea
              id="dig-room-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="dig-room-submit">
            Dig
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
