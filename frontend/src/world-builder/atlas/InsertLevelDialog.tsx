/**
 * InsertLevelDialog — grows the ladder around a node you already have. Opened
 * from a `FolioCrumb` insert point ("Arx City ⊕ The City Center"): name the
 * new level and pick which level it is, from the ones that fit between the two
 * (`insertableLevels`, highest first, so the default builds the ladder
 * top-down: a ward under a city first, then a neighborhood under the ward).
 *
 * Like `AddDialog`, this only assembles `{name, level}`; the caller
 * (`AtlasPage`) dispatches `create_area` and then moves the lower node inside
 * the new one.
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { insertableLevels } from './constants';
import type { FolioCrumbEntry } from './FolioCrumb';

export interface InsertLevelDialogProps {
  /** The pair to insert between; `null` keeps the dialog closed. */
  between: { upper: FolioCrumbEntry; lower: FolioCrumbEntry } | null;
  onClose: () => void;
  onConfirm: (payload: { name: string; level: number }) => void;
}

export function InsertLevelDialog({ between, onClose, onConfirm }: InsertLevelDialogProps) {
  const levels = between ? insertableLevels(between.upper, between.lower) : [];
  const [name, setName] = useState('');
  const [level, setLevel] = useState<number | null>(null);

  // Reset on each open: the pair decides which levels fit, and the highest is
  // the default because the ladder is built from the top down.
  useEffect(() => {
    if (!between) return;
    setName('');
    setLevel(insertableLevels(between.upper, between.lower)[0]?.value ?? null);
  }, [between]);

  const selectedLabel = levels.find((choice) => choice.value === level)?.label ?? 'level';
  const canSubmit = between != null && name.trim() !== '' && level != null;

  return (
    <Dialog open={between != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md" data-testid="insert-level-dialog">
        <DialogTitle className="font-body text-base font-normal">
          {between ? `Insert between ${between.upper.name} and ${between.lower.name}` : ''}
        </DialogTitle>
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline gap-2">
            <Label className="min-w-[6.5rem] shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
              Level
            </Label>
            <Select
              value={level != null ? String(level) : ''}
              onValueChange={(value) => setLevel(Number(value))}
            >
              <SelectTrigger className="flex-1" data-testid="insert-level-pick">
                <SelectValue placeholder="Pick a level" />
              </SelectTrigger>
              <SelectContent>
                {levels.map((choice) => (
                  <SelectItem key={choice.value} value={String(choice.value)}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="insert-level-name">{selectedLabel} name</Label>
            <Input
              id="insert-level-name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
              data-testid="insert-level-name"
            />
          </div>
          {between && (
            <p
              className="font-body text-xs italic text-muted-foreground"
              data-testid="insert-level-note"
            >
              {between.lower.name} moves inside the new {selectedLabel.toLowerCase()}, which takes
              its place on {between.upper.name}&apos;s map
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              if (level == null) return;
              onConfirm({ name: name.trim(), level });
              onClose();
            }}
            disabled={!canSubmit}
            data-testid="insert-level-submit"
          >
            Insert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
