/**
 * SettleAuraDialog (#5124, Screen 6 of the approved demo): the rite of settling.
 *
 * One rite carries out every reflection the character has written since their last rite.
 * The dialog lists them (what each is, the writing behind it, what the rite will do at a
 * full share), asks for one offering among the carried items that count, says what is
 * rolled, and performs the rite. The roll's outcome applies to every reflection, so the
 * result is a line per reflection under the outcome's name. The dialog reads the rite for
 * `characterSheetId` and performs it for that same character, so it can never write to
 * another character's aura.
 *
 * Opened by the sheet's "Settle your aura" button and by the feed's button after a
 * reflection posts; both show it only while a reflection waits. Solid Perform and an
 * outline Not now, both in the sheet's rust (`.aura-settle-dialog` in `sheet.css`, because
 * the dialog portals out of `.refsheet`).
 */

import { useState } from 'react';
import { Dialog, DialogContent, DialogTitle, NO_DESCRIPTION } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { pillClass } from '@/magic/components/pillClass';
import { usePerformSettlingRite, useSettlingRite } from '@/magic/queries';
import { offeringLabel } from '@/magic/riteText';
import type { RiteReflection, SettlingRiteResult } from '@/magic/types';

const ERROR_CLASS =
  'rounded-md border border-red-600/60 bg-red-50 p-3 text-sm font-medium text-red-800 dark:bg-red-950/40 dark:text-red-200';

/** The demo's outline button: a rust border and rust words, on the sheet's `--primary`. */
const RUST_OUTLINE = 'border-primary text-primary hover:bg-primary/10 hover:text-primary';

const LABEL_CLASS = 'text-xs font-semibold uppercase tracking-wide text-muted-foreground';

function rollLine(checkName: string, focusBonus: number): string {
  const focus = focusBonus > 0 ? `, +${focusBonus} from your worn focus` : '';
  return `Roll: ${checkName}${focus}. A full success carries out every reflection in full; a lesser one carries each out part of the way. The offering is spent whatever the roll.`;
}

function ReflectionBox({ reflection }: { reflection: RiteReflection }) {
  return (
    <div
      className="space-y-1 rounded-lg border border-border p-3"
      data-testid={`rite-reflection-${reflection.id}`}
    >
      <p className="font-semibold">{reflection.title}</p>
      {reflection.excerpt ? (
        <p className="text-sm italic text-muted-foreground">
          &ldquo;{reflection.excerpt}&rdquo;
          {reflection.from_line ? ` ${reflection.from_line}` : ''}
        </p>
      ) : null}
      <p className="text-sm">{reflection.effect_line}</p>
    </div>
  );
}

interface SettleAuraDialogProps {
  /** The character settling: the one whose reflections the rite takes. */
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettleAuraDialog({ characterSheetId, open, onOpenChange }: SettleAuraDialogProps) {
  const { data: reading } = useSettlingRite(characterSheetId, open);
  const perform = usePerformSettlingRite();
  const [pickedId, setPickedId] = useState<number | null>(null);
  const [result, setResult] = useState<SettlingRiteResult | null>(null);

  const offerings = reading?.offerings ?? [];
  // A lone offering is the choice; with several the player picks.
  const chosen =
    offerings.find((offering) => offering.item_id === pickedId) ??
    (offerings.length === 1 ? offerings[0] : null);
  const reflections = reading?.reflections ?? [];
  const ready = reading?.rite_ready ?? false;
  const canPerform = ready && chosen !== null && reflections.length > 0 && !perform.isPending;

  function handlePerform() {
    if (!chosen) return;
    perform.mutate(
      { character_sheet_id: characterSheetId, component_ids: [chosen.item_id] },
      { onSuccess: setResult }
    );
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      perform.reset();
      setResult(null);
      setPickedId(null);
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        {...NO_DESCRIPTION}
        className="aura-settle-dialog max-h-[90vh] space-y-3 overflow-y-auto"
      >
        <DialogTitle className="text-base font-semibold">Settling your aura</DialogTitle>

        {result ? (
          <div className="space-y-3">
            <output className="block space-y-1 text-sm" data-testid="rite-result">
              <span className="block font-semibold">{result.outcome_name}.</span>
              {result.lines.map((line, index) => (
                // Lines are the server's sentences in rite order; two may read alike.
                <span key={index} className="block">
                  {line}
                </span>
              ))}
            </output>
            <div className="flex justify-end">
              <Button
                variant="outline"
                className={RUST_OUTLINE}
                onClick={() => handleOpenChange(false)}
                data-testid="rite-close"
              >
                Close
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              You bring everything you have reflected on since your last rite.
            </p>

            <div className="space-y-2" data-testid="rite-reflections">
              {reflections.map((reflection) => (
                <ReflectionBox key={reflection.id} reflection={reflection} />
              ))}
            </div>

            {reading && !ready ? (
              <p className="text-sm text-muted-foreground" data-testid="rite-not-ready">
                {reading.not_ready_message}
              </p>
            ) : (
              <div className="space-y-2">
                <p className={LABEL_CLASS}>Offering</p>
                {offerings.length === 0 ? (
                  <p className="text-sm text-muted-foreground" data-testid="rite-no-offering">
                    You carry nothing that counts as the offering.
                  </p>
                ) : (
                  <fieldset
                    className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0"
                    aria-label="Offering"
                  >
                    {offerings.map((offering) => (
                      <button
                        key={offering.item_id}
                        type="button"
                        aria-pressed={chosen?.item_id === offering.item_id}
                        onClick={() => setPickedId(offering.item_id)}
                        data-testid={`rite-offering-${offering.item_id}`}
                        className={pillClass(chosen?.item_id === offering.item_id)}
                      >
                        {offeringLabel(offering)}
                      </button>
                    ))}
                  </fieldset>
                )}
                {reading?.check_name ? (
                  <p className="text-sm text-muted-foreground" data-testid="rite-roll">
                    {rollLine(reading.check_name, chosen?.focus_bonus ?? 0)}
                  </p>
                ) : null}
              </div>
            )}

            {perform.isError ? (
              <div role="alert" data-testid="rite-error" className={ERROR_CLASS}>
                {perform.error?.message || 'The rite did not take; please try again.'}
              </div>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                className={RUST_OUTLINE}
                onClick={() => handleOpenChange(false)}
                data-testid="settle-not-now"
              >
                Not now
              </Button>
              <Button onClick={handlePerform} disabled={!canPerform} data-testid="rite-perform">
                Perform the rite
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
