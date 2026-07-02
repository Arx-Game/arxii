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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import { DIRECTIONS } from '../gridMath';
import type { ManagerRoom, RoomBuilderActionKey, RoomSizeTier } from '../types';

const ALL_DIRECTIONS = [...Object.keys(DIRECTIONS), 'up', 'down'];

export interface DigDialogProps {
  /** The room the new room is dug from (the `room_id` anchor). */
  fromRoom: ManagerRoom;
  /** Locks the direction picker when launched from a ghost cell. */
  direction?: string;
  /** Prefills `like=` (exemplar copy) for the Duplicate affordance. */
  like?: string;
  sizeTiers: RoomSizeTier[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/**
 * Dig a stub room: direction + name required, everything else optional —
 * the ratified incremental rhythm. Refinement happens on the room panel
 * afterwards.
 */
export function DigDialog({
  fromRoom,
  direction: lockedDirection,
  like,
  sizeTiers,
  open,
  onOpenChange,
  runAction,
}: DigDialogProps) {
  const [direction, setDirection] = useState(lockedDirection ?? '');
  const [name, setName] = useState('');
  const [size, setSize] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (open) {
      setDirection(lockedDirection ?? '');
      setName('');
      setSize('');
      setDescription('');
    }
  }, [open, lockedDirection]);

  const canSubmit = direction.trim() !== '' && name.trim() !== '';

  const submit = () => {
    const kwargs: Record<string, unknown> = {
      room_id: fromRoom.id,
      direction,
      name: name.trim(),
    };
    if (size) kwargs.size = size;
    if (description.trim()) kwargs.description = description.trim();
    if (like) kwargs.like = like;
    runAction('dig_room', kwargs);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{like ? `Duplicate ${like}` : `Dig from ${fromRoom.name}`}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-direction">Direction</Label>
            <Select
              value={direction}
              onValueChange={setDirection}
              disabled={lockedDirection != null}
            >
              <SelectTrigger id="dig-direction">
                <SelectValue placeholder="Pick a direction" />
              </SelectTrigger>
              <SelectContent>
                {ALL_DIRECTIONS.map((dir) => (
                  <SelectItem key={dir} value={dir}>
                    {dir}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-name">Room name</Label>
            <Input
              id="dig-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Kitchen"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-size">Size (optional — defaults to Modest)</Label>
            <Select value={size} onValueChange={setSize} disabled={like != null}>
              <SelectTrigger id="dig-size">
                <SelectValue placeholder={like ? 'Copied from exemplar' : 'Default size'} />
              </SelectTrigger>
              <SelectContent>
                {sizeTiers.map((tier) => (
                  <SelectItem key={tier.id} value={tier.name}>
                    {tier.name} ({tier.units} units)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dig-description">Description (optional)</Label>
            <Textarea
              id="dig-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={like ? 'Copied from exemplar unless set' : 'An unfinished room.'}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="dig-submit">
            Dig
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
