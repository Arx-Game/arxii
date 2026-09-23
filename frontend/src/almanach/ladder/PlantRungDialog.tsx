/**
 * PlantRungDialog (#3983 Task 8, plate II "Plant a rung") — mints one named
 * or unclaimed county/barony under an existing rung. Tier is fixed to
 * county/barony (never march — the plant flow only ever extends an existing
 * duchy or county's own chain, #3983 Task 8 brief); planting a county also
 * seeds its own seat barony server-side (`almanach.plant_rung`), so the
 * "comes with" line previews that for the county pick only. Held-by mirrors
 * the plate's seg toggle: Unclaimed (the default, `held_by_org_id: null`)
 * or a house on record, picked from `useHouses(realmId)` — the same list
 * Task 8's contents rail renders.
 *
 * Follows `world-builder/atlas/AddDialog.tsx`'s dialog shape (`Dialog` /
 * `DialogContent` / `DialogFooter` / `DialogTitle` from `@/components/ui/
 * dialog`, Cancel outlined + a primary submit) but keeps a visible heading
 * (`DialogTitle`, not screen-reader-only) since the plate draws one.
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

import { useHouses } from '../queries';
import { STATES } from '../copy';
import type { LadderParentRef } from './tree';

type PlantTier = 'county' | 'barony';

export interface PlantRungPayload {
  tier: PlantTier;
  name: string;
  held_by_org_id: number | null;
}

export interface PlantRungDialogProps {
  parent: LadderParentRef;
  open: boolean;
  onClose: () => void;
  onConfirm: (payload: PlantRungPayload) => void;
  /** Feeds the "a house on record" pick (`useHouses`); omitted in isolation (no houses offered). */
  realmId?: number;
}

const TIER_CHOICES: { value: PlantTier; label: string }[] = [
  { value: 'county', label: 'county' },
  { value: 'barony', label: 'barony' },
];

export function PlantRungDialog({
  parent,
  open,
  onClose,
  onConfirm,
  realmId,
}: PlantRungDialogProps) {
  const [tier, setTier] = useState<PlantTier>('county');
  const [name, setName] = useState('');
  const [heldByHouse, setHeldByHouse] = useState(false);
  const [houseId, setHouseId] = useState('');
  const { data: housesPayload } = useHouses(heldByHouse ? realmId : undefined);
  const houses = housesPayload?.results ?? [];

  useEffect(() => {
    if (!open) return;
    setTier('county');
    setName('');
    setHeldByHouse(false);
    setHouseId('');
  }, [open, parent.title_id]);

  const trimmedName = name.trim();
  const canSubmit = trimmedName !== '';

  const submit = () => {
    if (!canSubmit) return;
    onConfirm({
      tier,
      name: trimmedName,
      held_by_org_id: heldByHouse && houseId !== '' ? Number(houseId) : null,
    });
    onClose();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="almanach max-w-md">
        <DialogTitle>Plant a rung</DialogTitle>
        <div className="row2">
          <div className="field">
            <span className="label">under</span>
            <div className="val">
              {parent.name} <span className="meta">{parent.tier}</span>
            </div>
          </div>
          <div className="field">
            <span className="label">tier</span>
            <div className="seg" role="group" aria-label="Tier">
              {TIER_CHOICES.map((choice) => (
                <button
                  key={choice.value}
                  type="button"
                  aria-pressed={tier === choice.value}
                  onClick={() => setTier(choice.value)}
                >
                  {choice.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="field">
          <Label htmlFor="plant-rung-name">name</Label>
          <Input
            id="plant-rung-name"
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
          />
        </div>
        {tier === 'county' && (
          <div className="field">
            <span className="label">comes with</span>
            <div className="val">
              1 barony, the seat <span className="chip undef">{STATES.undefined}</span>
            </div>
          </div>
        )}
        <div className="field">
          <span className="label">held by</span>
          <div className="seg" role="group" aria-label="Held by">
            <button type="button" aria-pressed={!heldByHouse} onClick={() => setHeldByHouse(false)}>
              {STATES.unclaimed}
            </button>
            <button type="button" aria-pressed={heldByHouse} onClick={() => setHeldByHouse(true)}>
              a house on record
            </button>
          </div>
        </div>
        {heldByHouse && (
          <div className="field">
            <Label htmlFor="plant-rung-house">house</Label>
            <Select value={houseId} onValueChange={setHouseId}>
              <SelectTrigger id="plant-rung-house">
                <SelectValue placeholder="pick a house" />
              </SelectTrigger>
              <SelectContent>
                {houses.map((house) => (
                  <SelectItem key={house.id} value={String(house.id)}>
                    {house.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={submit} disabled={!canSubmit}>
            Plant
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
