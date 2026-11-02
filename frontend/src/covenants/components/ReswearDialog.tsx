/**
 * The Rite of Re-swearing (#4940, demo screen 9): give up one chosen vow pick for another
 * of the same level.
 *
 * Opened from the vow picks panel's Change picks. "Give up" lists the vow's chosen picks;
 * "Take instead" lists the other picks at the given-up pick's level, a pick that would
 * leave the level over its budget dimmed with why. The level before and after the swap
 * and the rite's cost (the action points `respec_ap_cost` sets, its anima and its
 * components) sit under them. The rite is the authored one the options endpoint names,
 * performed through the ritual perform endpoint with the carried items that pay it; the
 * server refuses (and says why) in a fight or short of action points.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, NO_DESCRIPTION } from '@/components/ui/dialog';
import type { VowPickCatalog, VowPickEntry, VowPickLevel } from '../api';
import { useReswearOptions, useReswearPick } from '../queries';

function points(price: number): string {
  return `${price} ${price === 1 ? 'pt' : 'pts'}`;
}

interface Chosen {
  level: VowPickLevel;
  pick: VowPickEntry;
}

function chosenPicks(catalog: VowPickCatalog): Chosen[] {
  return catalog.levels.flatMap((level) =>
    level.picks.filter((pick) => pick.chosen).map((pick) => ({ level, pick }))
  );
}

function ledger(level: VowPickLevel, spent: number, names: string[]): string {
  return `${spent} of ${level.budget} · ${names.join(', ')}`;
}

function PickChoice({
  pick,
  pressed,
  disabled,
  note,
  onPick,
}: {
  pick: VowPickEntry;
  pressed: boolean;
  disabled?: boolean;
  note?: string;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onPick}
      data-testid="reswear-pick"
      className={`vowpicks-entry vowpicks-swap ${pressed ? 'vowpicks-chosen' : ''} ${
        disabled ? 'vowpicks-locked' : ''
      }`}
    >
      <span className="vowpicks-mark">{pressed ? '◆' : '◇'}</span>
      <span className="refsheet-entry-name">{pick.name}</span>
      <span className="refsheet-note">{points(pick.price)}</span>
      {note && <span className="vowpicks-mech">{note}</span>}
    </button>
  );
}

interface ReswearDialogProps {
  catalog: VowPickCatalog;
  sheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: (message: string) => void;
}

export function ReswearDialog({
  catalog,
  sheetId,
  open,
  onOpenChange,
  onDone,
}: ReswearDialogProps) {
  const { data: options } = useReswearOptions(sheetId, open);
  const reswear = useReswearPick(sheetId);
  const chosen = chosenPicks(catalog);
  const [oldId, setOldId] = useState<number | null>(null);
  const [newId, setNewId] = useState<number | null>(null);

  const given = chosen.find((row) => row.pick.id === oldId) ?? chosen[0];
  const level = given?.level;
  const left = level && given ? level.budget - level.spent + given.pick.price : 0;
  const candidates = level ? level.picks.filter((pick) => !pick.chosen) : [];
  const fits = (pick: VowPickEntry) => pick.price <= left;
  const taken = candidates.find((pick) => pick.id === newId && fits(pick)) ?? candidates.find(fits);
  const ritualId = options?.ritual_id ?? null;

  const keptNames = level ? level.picks.filter((p) => p.chosen).map((p) => p.name) : [];
  const afterNames = keptNames.map((name) => (name === given?.pick.name ? taken?.name : name));
  const cost = [
    `${options?.ap_cost ?? 0} AP from this week`,
    ...(options?.anima_cost ? [`${options.anima_cost} anima`] : []),
    ...(options?.components ?? []),
  ].join(' · ');

  function pickOld(pickId: number) {
    reswear.reset();
    setOldId(pickId);
    setNewId(null);
  }

  function pickNew(pickId: number) {
    reswear.reset();
    setNewId(pickId);
  }

  function perform() {
    if (ritualId === null || !given || !taken) return;
    reswear.mutate(
      {
        ritualId,
        covenantId: catalog.covenant_id,
        oldPickId: given.pick.id,
        newPickId: taken.id,
        componentIds: options?.component_ids ?? [],
      },
      {
        onSuccess: (message) => {
          onDone(message);
          onOpenChange(false);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        {...NO_DESCRIPTION}
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        data-testid="reswear-dialog"
      >
        <div className="refsheet vowpicks-rite">
          <div className="vowpicks-head vowpicks-rite-head">
            <DialogTitle className="refsheet-subheading">Rite of Re-swearing</DialogTitle>
            {level && (
              <span className="refsheet-note">
                {catalog.vow} · level {level.level}
              </span>
            )}
          </div>

          {options?.unavailable_reason ? (
            <output className="refsheet-note block">{options.unavailable_reason}</output>
          ) : null}

          {given && level ? (
            <>
              <div className="vowpicks-two">
                <div className="vowpicks-level">
                  <h3 className="refsheet-subheading">Give up</h3>
                  {chosen.map((row) => (
                    <PickChoice
                      key={row.pick.id}
                      pick={row.pick}
                      pressed={row.pick.id === given.pick.id}
                      onPick={() => pickOld(row.pick.id)}
                    />
                  ))}
                </div>
                <div className="vowpicks-level">
                  <h3 className="refsheet-subheading">Take instead</h3>
                  {candidates.map((pick) => (
                    <PickChoice
                      key={pick.id}
                      pick={pick}
                      pressed={pick.id === taken?.id}
                      disabled={!fits(pick)}
                      note={fits(pick) ? undefined : 'costs more than is left'}
                      onPick={() => pickNew(pick.id)}
                    />
                  ))}
                </div>
              </div>

              <div className="vowpicks-ledger" data-testid="reswear-before">
                <span>Level {level.level} before</span>
                <span>{ledger(level, level.spent, keptNames)}</span>
              </div>
              {taken && (
                <div className="vowpicks-ledger" data-testid="reswear-after">
                  <span>Level {level.level} after</span>
                  <span>
                    {ledger(
                      level,
                      level.spent - given.pick.price + taken.price,
                      afterNames.filter((name): name is string => Boolean(name))
                    )}
                  </span>
                </div>
              )}
              <div className="vowpicks-ledger" data-testid="reswear-cost">
                <span>Cost</span>
                <span>{cost}</span>
              </div>
            </>
          ) : null}

          {reswear.isError && (
            <p className="refsheet-note vowpicks-error" role="alert">
              {reswear.error.message}
            </p>
          )}

          <div className="vowpicks-rite-foot">
            <span className="refsheet-note vowpicks-locked-note">Not during a fight.</span>
            <Button
              type="button"
              onClick={perform}
              disabled={ritualId === null || !taken || reswear.isPending}
              data-testid="reswear-perform"
            >
              Perform the rite
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
