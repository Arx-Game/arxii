/**
 * "Harvest Primum" (#5125): draw out one of the Primum the viewer senses here. A pick of what
 * is on offer, the check she rolls, Cancel and Harvest, then the server's answer inside the
 * block. The caller holds the answer, so it stays on screen when the lair empties.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import type { HarvestOffer } from '@/hooks/types';
import { offerLabel, runHarvest, type HarvestAnswer } from '../harvestAnswer';
import { HarvestAnswerLines } from './HarvestAnswerLines';

interface HarvestPanelProps {
  offers: HarvestOffer[];
  characterId: number;
  answer: HarvestAnswer | null;
  onAnswer: (answer: HarvestAnswer | null) => void;
  onCancel: () => void;
}

function optionLabel(offer: HarvestOffer): string {
  return offer.opponent_id === null
    ? offerLabel(offer)
    : `${offerLabel(offer)} · ${offer.opponent_name}`;
}

export function HarvestPanel({
  offers,
  characterId,
  answer,
  onAnswer,
  onCancel,
}: HarvestPanelProps) {
  const dispatch = useDispatchPlayerAction(characterId);
  const [picked, setPicked] = useState(0);
  const offer = offers[Math.min(picked, offers.length - 1)];
  const checkName = offers.find((row) => row.check_name)?.check_name;
  const apCost = offers.find((row) => row.ap_cost > 0)?.ap_cost;

  return (
    <div className="space-y-2" data-testid="harvest-panel">
      <h4 className="text-xs font-semibold">Harvest Primum</h4>
      {offer && (
        <>
          <fieldset className="space-y-1">
            <legend className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Draw out
            </legend>
            {offers.map((row, index) => (
              <label
                key={`${row.substance_id}-${row.opponent_id ?? 'place'}`}
                className="flex items-center gap-2 text-xs"
              >
                <input
                  type="radio"
                  name="harvest-pick"
                  checked={index === Math.min(picked, offers.length - 1)}
                  onChange={() => setPicked(index)}
                />
                {optionLabel(row)}
              </label>
            ))}
          </fieldset>
          {checkName && <p className="text-xs text-muted-foreground">Check: {checkName}</p>}
          {apCost && <p className="text-xs text-muted-foreground">Costs {apCost} AP</p>}
        </>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        {offer && (
          <Button
            type="button"
            size="sm"
            disabled={dispatch.isPending}
            onClick={() => {
              void runHarvest(dispatch.mutateAsync, offer).then(onAnswer);
            }}
          >
            Harvest
          </Button>
        )}
      </div>
      {answer && <HarvestAnswerLines answer={answer} />}
    </div>
  );
}
