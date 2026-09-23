/**
 * PlantRungDialog (#3983 Task 8, plate II "Plant a rung"; root-planting
 * final review I9) — mints one named or unclaimed rung under an existing
 * one, OR — with no parent, or with `allowRoot` while the level bar sits on
 * the ladder's own top tier — a root rung with no `parent_title_id` (the
 * only way to lay a realm's very first kingdom/duchy, or a second one
 * beside it). Tier choices are always strictly deeper than the parent's own
 * tier (`tierChoicesFor`, never `march` — the plant flow only ever extends
 * an existing chain in county/barony steps, #3983 Task 8 brief; final
 * review M7 — a barony parent offers no choices at all, since nothing
 * plants under a barony) or, at the root, `empire`/`kingdom`/`duchy`.
 * Planting a county also seeds its own seat barony server-side
 * (`almanach.plant_rung`), so the "comes with" line previews that for the
 * county pick only. Held-by mirrors the plate's seg toggle: Unclaimed (the
 * default, `held_by_org_id: null`) or a house on record, picked from
 * `useHouses(realmId)` — the same list Task 8's contents rail renders.
 *
 * With a real parent AND `allowRoot`, a "plant" seg lets the caller switch
 * between "under <parent>" (the default — every existing caller/test that
 * doesn't pass `allowRoot` never sees this seg, so the old single-target
 * behavior is unchanged) and "at the realm root"; with no parent at all
 * (`AlmanachPage`'s empty-ladder case) the dialog opens straight into root
 * mode with no seg to toggle away from (there's nothing to nest under yet).
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
import { TIER_ORDER, type LadderParentRef, type Tier } from './tree';

type PlantTier = Exclude<Tier, 'march'>;

export interface PlantRungPayload {
  tier: PlantTier;
  name: string;
  held_by_org_id: number | null;
  /** Present (and `true`) only when the rung was planted at the realm
   * root — omitted, not `false`, for every existing "under a parent" call
   * so callers that pre-date root-planting see the exact same payload
   * shape they always have. */
  atRoot?: boolean;
}

export interface PlantRungDialogProps {
  /** `null` plants at the realm root unconditionally (no parent to nest
   * under yet — `AlmanachPage`'s empty-ladder case). */
  parent: LadderParentRef | null;
  /** Whether the root-vs-under-parent seg is offered at all (final review
   * I9: when the level bar sits on the ladder's own top tier). Ignored
   * when `parent` is already `null` — root is the only option then. */
  allowRoot?: boolean;
  open: boolean;
  onClose: () => void;
  onConfirm: (payload: PlantRungPayload) => void;
  /** Feeds the "a house on record" pick (`useHouses`); omitted in isolation (no houses offered). */
  realmId?: number;
}

const ROOT_TIER_CHOICES: { value: PlantTier; label: string }[] = [
  { value: 'empire', label: 'empire' },
  { value: 'kingdom', label: 'kingdom' },
  { value: 'duchy', label: 'duchy' },
];

const NESTED_TIER_CHOICES: { value: PlantTier; label: string }[] = [
  { value: 'county', label: 'county' },
  { value: 'barony', label: 'barony' },
];

/** The tiers `plant` may offer: root choices with no parent tier, else
 * whatever `NESTED_TIER_CHOICES` sits strictly deeper than the parent's own
 * tier (final review M7 — a barony parent offers none; a county parent
 * offers only barony; a duchy-or-shallower parent offers both, matching the
 * pre-I9 default). Takes the parent's own tier STRING rather than the full
 * `LadderParentRef` deliberately — `parent` itself is a fresh object
 * literal every caller render, so anything that closes over it (the reset
 * `useEffect` below) keys on this primitive instead, exactly like the
 * `parent.title_id` dependency beside it. */
function tierChoicesFor(parentTier: string | null): { value: PlantTier; label: string }[] {
  if (parentTier === null) return ROOT_TIER_CHOICES;
  const parentIndex = TIER_ORDER.indexOf(parentTier as Tier);
  return NESTED_TIER_CHOICES.filter((choice) => TIER_ORDER.indexOf(choice.value) > parentIndex);
}

export function PlantRungDialog({
  parent,
  allowRoot = false,
  open,
  onClose,
  onConfirm,
  realmId,
}: PlantRungDialogProps) {
  // No parent at all forces root mode permanently (nothing to nest under);
  // otherwise root starts OFF so every pre-I9 caller/test sees the exact
  // same default "under <parent>" dialog it always has. Both derived as
  // primitives (never the `parent` object itself, a fresh literal every
  // caller render) so the reset `useEffect` below can depend on them
  // exhaustively without re-running on every unrelated re-render.
  const hasParent = parent !== null;
  const parentTitleId = parent?.title_id ?? null;
  const parentTier = parent?.tier ?? null;
  const [atRoot, setAtRoot] = useState(!hasParent);
  const [tier, setTier] = useState<PlantTier>(
    () => tierChoicesFor(hasParent ? parentTier : null)[0]?.value ?? 'county'
  );
  const [name, setName] = useState('');
  const [heldByHouse, setHeldByHouse] = useState(false);
  const [houseId, setHouseId] = useState('');
  const { data: housesPayload } = useHouses(heldByHouse ? realmId : undefined);
  const houses = housesPayload?.results ?? [];

  const choices = tierChoicesFor(atRoot ? null : parentTier);
  const canOfferRoot = hasParent && allowRoot;

  useEffect(() => {
    if (!open) return;
    const initialAtRoot = !hasParent;
    setAtRoot(initialAtRoot);
    setTier(tierChoicesFor(initialAtRoot ? null : parentTier)[0]?.value ?? 'county');
    setName('');
    setHeldByHouse(false);
    setHouseId('');
  }, [open, hasParent, parentTitleId, parentTier]);

  const setPlantLocation = (nextAtRoot: boolean) => {
    setAtRoot(nextAtRoot);
    setTier(tierChoicesFor(nextAtRoot ? null : parentTier)[0]?.value ?? 'county');
  };

  const trimmedName = name.trim();
  const canSubmit = trimmedName !== '' && choices.some((choice) => choice.value === tier);

  const submit = () => {
    if (!canSubmit) return;
    onConfirm({
      tier,
      name: trimmedName,
      held_by_org_id: heldByHouse && houseId !== '' ? Number(houseId) : null,
      ...(atRoot ? { atRoot: true } : {}),
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
        {canOfferRoot && parent && (
          <div className="field">
            <span className="label">plant</span>
            <div className="seg" role="group" aria-label="Plant location">
              <button type="button" aria-pressed={!atRoot} onClick={() => setPlantLocation(false)}>
                under {parent.name}
              </button>
              <button type="button" aria-pressed={atRoot} onClick={() => setPlantLocation(true)}>
                at the realm root
              </button>
            </div>
          </div>
        )}
        <div className="row2">
          <div className="field">
            <span className="label">under</span>
            <div className="val">
              {atRoot || !parent ? (
                'the realm'
              ) : (
                <>
                  {parent.name} <span className="meta">{parent.tier}</span>
                </>
              )}
            </div>
          </div>
          <div className="field">
            <span className="label">tier</span>
            <div className="seg" role="group" aria-label="Tier">
              {choices.map((choice) => (
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
              1 barony, the seat <span className="chip undef">{STATES.undefined}</span> · hall{' '}
              <span className="chip undef">{STATES.undefined}</span>
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
