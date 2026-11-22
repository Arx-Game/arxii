/**
 * AnimaRitualAttuneDialog (#5280, Screen 4 of the approved demo): pay to change the anima
 * ritual's two resonance picks after the free first setup.
 *
 * The cost rows read the staff-set attunement costs the choices endpoint carries; a cost of 0
 * still shows 0, and the Roll row appears only when staff set a check. The resonance cost is
 * paid in each newly picked resonance, so its label names them. A refusal is a plain sentence
 * in the 400 `detail`, shown as the dialog's error; a failed roll is a 200 whose message is shown
 * and leaves the dialog open.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { extractErrorMessage } from '@/lib/errors';
import type { AnimaRitualChoices } from '@/rituals/api';
import { useAttuneAnimaRitual } from '@/rituals/queries';
import { AnimaRitualPillPicker } from './AnimaRitualPillPicker';

interface AnimaRitualAttuneDialogProps {
  characterSheetId: number;
  choices: AnimaRitualChoices;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AnimaRitualAttuneDialog({
  characterSheetId,
  choices,
  open,
  onOpenChange,
}: AnimaRitualAttuneDialogProps) {
  const [primalId, setPrimalId] = useState<number | null>(choices.primal_pick?.id ?? null);
  const [outwardId, setOutwardId] = useState<number | null>(choices.outward_pick?.id ?? null);
  const [notice, setNotice] = useState<string | null>(null);
  const attune = useAttuneAnimaRitual();

  const currentPrimalId = choices.primal_pick?.id ?? null;
  const currentOutwardId = choices.outward_pick?.id ?? null;
  const changed = primalId !== currentPrimalId || outwardId !== currentOutwardId;
  const { anima_cost, resonance_cost, ap_cost, check_type_name } = choices.attunement;

  const newlyPicked: string[] = [];
  if (primalId !== null && primalId !== currentPrimalId) {
    const pick = choices.primal.find((r) => r.id === primalId);
    if (pick) newlyPicked.push(pick.name);
  }
  if (outwardId !== null && outwardId !== currentOutwardId) {
    const pick = choices.outward.find((r) => r.id === outwardId);
    if (pick) newlyPicked.push(pick.name);
  }
  const resonanceLabel =
    newlyPicked.length > 0 ? `Resonance cost (${newlyPicked.join(', ')})` : 'Resonance cost';

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setPrimalId(currentPrimalId);
      setOutwardId(currentOutwardId);
      setNotice(null);
      attune.reset();
    }
  }

  function handleAttune() {
    setNotice(null);
    attune.mutate(
      {
        character_sheet_id: characterSheetId,
        primal_resonance_id: primalId,
        outward_resonance_id: outwardId,
      },
      {
        onSuccess: (result) => {
          if (result.changed) {
            toast.success(result.message);
            onOpenChange(false);
          } else {
            setNotice(result.message);
          }
        },
      }
    );
  }

  const errorMessage = attune.isError
    ? extractErrorMessage(attune.error, 'Failed to attune your ritual')
    : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg" {...NO_DESCRIPTION}>
        <DialogHeader>
          <DialogTitle>Attune your ritual</DialogTitle>
        </DialogHeader>

        {errorMessage && (
          <div
            role="alert"
            className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
            data-testid="anima-ritual-attune-error"
          >
            {errorMessage}
          </div>
        )}
        {notice && (
          <p
            role="status"
            className="rounded-md bg-muted px-4 py-3 text-sm"
            data-testid="anima-ritual-attune-notice"
          >
            {notice}
          </p>
        )}

        <div className="flex flex-wrap gap-4">
          <AnimaRitualPillPicker
            label="What you feel"
            resonances={choices.primal}
            selectedId={primalId}
            onSelect={setPrimalId}
            disabled={attune.isPending}
            testId="attune-primal-picker"
            keptUnheld={choices.primal_pick}
          />
          <AnimaRitualPillPicker
            label="What it does to them"
            resonances={choices.outward}
            selectedId={outwardId}
            onSelect={setOutwardId}
            allowNone
            disabled={attune.isPending}
            testId="attune-outward-picker"
            keptUnheld={choices.outward_pick}
          />
        </div>

        <dl
          className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm tabular-nums"
          data-testid="anima-ritual-attune-costs"
        >
          <dt>Anima</dt>
          <dd>{anima_cost}</dd>
          <dt>{resonanceLabel}</dt>
          <dd>{resonance_cost}</dd>
          <dt>Action points</dt>
          <dd>{ap_cost}</dd>
          {check_type_name && (
            <>
              <dt>Roll</dt>
              <dd>{check_type_name}</dd>
            </>
          )}
        </dl>

        <DialogFooter>
          <Button type="button" onClick={handleAttune} disabled={!changed || attune.isPending}>
            {attune.isPending ? 'Attuning...' : 'Attune'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={attune.isPending}
          >
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
