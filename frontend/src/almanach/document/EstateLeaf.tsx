/**
 * EstateLeaf (#3983 Task 9, plate S-VII "The Estate") — the house's
 * residence in the capital: name / district / held / prose / rooms `—`,
 * read-only. `almanach_plan_estate` (`AlmanachPlanEstateAction.execute`,
 * `almanach.py`) is the only estate mutation and it always PLANTS a new
 * estate `Area` (`city_area_id` required every call, no update path) — so
 * once `estate` is non-empty there is nothing here to Save; the "plan the
 * estate" dialog only appears when the house has none yet.
 *
 * The plate's own "on the Atlas" pin field is left out here — decision 6
 * doesn't call for it, and it needs the same area picker that isn't on the
 * wire (the third pre-approved omission): there's no way to plot or even
 * confirm an estate's map position without one, so showing a pin (even a
 * link) would be guessing at a location this payload doesn't carry.
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { DISTRICT } from '../copy';
import type { AlmanachEstateEntry } from '../types';

export interface PlanEstateFields {
  city_area_id: number;
  name: string;
  description: string;
  district_area_id?: number;
}

export interface EstateLeafProps {
  estate: AlmanachEstateEntry[];
  onPlan: (fields: PlanEstateFields) => void;
}

export function EstateLeaf({ estate, onPlan }: EstateLeafProps) {
  const [planOpen, setPlanOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [cityAreaId, setCityAreaId] = useState('');
  const [districtAreaId, setDistrictAreaId] = useState('');

  useEffect(() => {
    if (!planOpen) return;
    setName('');
    setDescription('');
    setCityAreaId('');
    setDistrictAreaId('');
  }, [planOpen]);

  const canSubmit = name.trim() !== '' && cityAreaId.trim() !== '';

  const submit = () => {
    if (!canSubmit) return;
    onPlan({
      city_area_id: Number(cityAreaId),
      name: name.trim(),
      description,
      ...(districtAreaId.trim() !== '' ? { district_area_id: Number(districtAreaId) } : {}),
    });
    setPlanOpen(false);
  };

  const first = estate[0] ?? null;

  return (
    <main className="chapter">
      <h3>Estate</h3>
      {first ? (
        <>
          <div className="row3">
            <div className="field">
              <span className="label">name</span>
              <div className="val">{first.name}</div>
            </div>
            <div className="field">
              <span className="label">{DISTRICT}</span>
              <div className="val">
                {first.district !== '' ? first.district : <abbr title="none">—</abbr>}
              </div>
            </div>
            <div className="field">
              <span className="label">held</span>
              <div className="val">by the house</div>
            </div>
          </div>
          <div className={first.description === '' ? 'prose empty' : 'prose'}>
            {first.description === '' ? 'PLACEHOLDER' : first.description}
          </div>
          <div className="field">
            <span className="label">rooms</span>
            <div className="val">
              <abbr title="none">—</abbr>
            </div>
          </div>
        </>
      ) : (
        <div className="savebar">
          <span className="note">no estate planted yet</span>
          <button type="button" className="btn" onClick={() => setPlanOpen(true)}>
            plan the estate
          </button>
        </div>
      )}
      <Dialog
        open={planOpen}
        onOpenChange={(next) => {
          if (!next) setPlanOpen(false);
        }}
      >
        <DialogContent className="almanach max-w-md">
          <DialogTitle>Plan the estate</DialogTitle>
          <div className="field">
            <Label htmlFor="plan-estate-name">name</Label>
            <Input
              id="plan-estate-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <Label htmlFor="plan-estate-description">description</Label>
            <Textarea
              id="plan-estate-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="row2">
            <div className="field">
              <Label htmlFor="plan-estate-city">city area id</Label>
              <Input
                id="plan-estate-city"
                type="number"
                min={1}
                value={cityAreaId}
                onChange={(e) => setCityAreaId(e.target.value)}
              />
            </div>
            <div className="field">
              <Label htmlFor="plan-estate-district">district area id</Label>
              <Input
                id="plan-estate-district"
                type="number"
                min={1}
                value={districtAreaId}
                onChange={(e) => setDistrictAreaId(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPlanOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={submit} disabled={!canSubmit}>
              Plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
