/**
 * Extracting Primum from a slain creature (#5125): what the viewer senses in its remains,
 * the check she rolls, a Harvest button per offer, and the server's answer. Nothing at all
 * with no offers and no answer. The caller holds the answer, so it stays after the foe is
 * no longer offered.
 */
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import type { HarvestOffer } from '@/hooks/types';
import { checkLine, primumName, runHarvest, type HarvestAnswer } from '../harvestAnswer';
import { HarvestAnswerLines } from './HarvestAnswerLines';

interface HarvestRowProps {
  offers: HarvestOffer[];
  /** The played character who presses Harvest. */
  characterId: number;
  answer?: HarvestAnswer | null;
  onAnswer?: (answer: HarvestAnswer) => void;
}

export function HarvestRow({ offers, characterId, answer = null, onAnswer }: HarvestRowProps) {
  const dispatch = useDispatchPlayerAction(characterId);

  if (offers.length === 0 && !answer) {
    return null;
  }

  const check = checkLine(offers.find((offer) => offer.check_name));
  const apCost = offers.find((offer) => offer.ap_cost > 0)?.ap_cost;
  const names = [...new Set(offers.map((offer) => offer.substance_name))];

  return (
    <div className="space-y-1" data-testid="harvest-row">
      {names.map((name) => (
        <p key={name} className="text-xs">
          You sense {name} Primum in its remains.
        </p>
      ))}
      {check && <p className="text-xs text-muted-foreground">{check}</p>}
      {apCost && <p className="text-xs text-muted-foreground">Costs {apCost} AP</p>}
      {offers.map((offer) => (
        <Button
          key={offer.substance_id}
          type="button"
          size="sm"
          variant="outline"
          className="h-6 px-2 text-xs"
          disabled={dispatch.isPending}
          onClick={() => {
            void runHarvest(dispatch.mutateAsync, offer).then((result) => onAnswer?.(result));
          }}
        >
          {offers.length > 1 ? `Harvest ${primumName(offer.substance_name)}` : 'Harvest'}
        </Button>
      ))}
      {answer && <HarvestAnswerLines answer={answer} />}
    </div>
  );
}
