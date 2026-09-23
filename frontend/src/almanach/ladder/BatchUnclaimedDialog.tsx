/**
 * BatchUnclaimedDialog (#3983 Task 8, plate II "Batch unclaimed") — mints
 * several Undefined, Unclaimed rungs under a parent in one dispatch
 * (`almanach_batch_unclaimed`). Tier fixed to county/barony like
 * `PlantRungDialog`. Picking county asks two counts (how many counties, how
 * many baronies each — `count` and `baronies_per_county`); picking barony
 * mints baronies directly under the parent and drops the per-county count
 * (baronies have no chain below them, `almanach._CHAIN_BELOW[BARONY] ==
 * ()`). The submit button previews the mint ("Mint 2 counties, 4
 * baronies"), matching the plate's own submit copy instead of a bare "Add".
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { STATES } from '../copy';
import type { LadderParentRef } from './tree';
import { tierNoun } from './tree';

type BatchTier = 'county' | 'barony';

export interface BatchUnclaimedPayload {
  tier: BatchTier;
  count: number;
  baronies_per_county?: number;
}

export interface BatchUnclaimedDialogProps {
  parent: LadderParentRef;
  open: boolean;
  onClose: () => void;
  onConfirm: (payload: BatchUnclaimedPayload) => void;
}

const TIER_CHOICES: { value: BatchTier; label: string }[] = [
  { value: 'county', label: 'county' },
  { value: 'barony', label: 'barony' },
];

function toPositiveInt(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function BatchUnclaimedDialog({
  parent,
  open,
  onClose,
  onConfirm,
}: BatchUnclaimedDialogProps) {
  const [tier, setTier] = useState<BatchTier>('county');
  const [count, setCount] = useState('2');
  const [baroniesPerCounty, setBaroniesPerCounty] = useState('2');

  useEffect(() => {
    if (!open) return;
    setTier('county');
    setCount('2');
    setBaroniesPerCounty('2');
  }, [open, parent.title_id]);

  const countNum = toPositiveInt(count);
  const perCountyNum = toPositiveInt(baroniesPerCounty);
  const totalBaronies = tier === 'county' ? countNum * perCountyNum : countNum;
  const canSubmit = tier === 'county' ? countNum > 0 && perCountyNum > 0 : countNum > 0;

  const mintLabel =
    tier === 'county'
      ? `Mint ${countNum} ${tierNoun('county', countNum)}, ${totalBaronies} ${tierNoun('barony', totalBaronies)}`
      : `Mint ${countNum} ${tierNoun('barony', countNum)}`;

  const submit = () => {
    if (!canSubmit) return;
    onConfirm({
      tier,
      count: countNum,
      ...(tier === 'county' ? { baronies_per_county: perCountyNum } : {}),
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
        <DialogTitle>Batch unclaimed</DialogTitle>
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
        <div className="row2">
          <div className="field">
            <Label htmlFor="batch-count">{tier === 'county' ? 'counties' : 'baronies'}</Label>
            <Input
              id="batch-count"
              type="number"
              min={1}
              value={count}
              onChange={(event) => setCount(event.target.value)}
            />
          </div>
          {tier === 'county' && (
            <div className="field">
              <Label htmlFor="batch-per-county">baronies in each</Label>
              <Input
                id="batch-per-county"
                type="number"
                min={1}
                value={baroniesPerCounty}
                onChange={(event) => setBaroniesPerCounty(event.target.value)}
              />
            </div>
          )}
        </div>
        {tier === 'county' && (
          <div className="field">
            <span className="label">each county</span>
            <div className="val">
              seat barony <span className="chip undef">{STATES.undefined}</span> · demesne unplaced
            </div>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={submit} disabled={!canSubmit}>
            {mintLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
