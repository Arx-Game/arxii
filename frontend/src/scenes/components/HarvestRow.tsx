/**
 * Extracting Primum (#5125): one Harvest button per offer, wherever the server says the
 * viewer perceives Primum she can take: a lair she stands in, or a slain creature. The
 * server answers in one plain sentence either way, so the button only reports it.
 */
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import type { HarvestOffer } from '@/hooks/types';
import { primumName } from '../primumName';

interface HarvestRowProps {
  offers: HarvestOffer[];
  characterId: number;
  /** Called after any answer, so a caller can refetch what the harvest changed. */
  onHarvested?: () => void;
}

export function HarvestRow({ offers, characterId, onHarvested }: HarvestRowProps) {
  const dispatch = useDispatchPlayerAction(characterId);

  if (offers.length === 0) {
    return null;
  }

  const harvest = async (offer: HarvestOffer) => {
    try {
      const result = await dispatch.mutateAsync({
        ref: { backend: 'registry', registry_key: 'harvest_primum' },
        kwargs: { substance: offer.substance_id, opponent_id: offer.opponent_id },
      });
      if (isDispatchFailure(result)) {
        toast.error(result.message ?? 'You could not extract it.');
      } else if (result.message) {
        toast.success(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'You could not extract it.');
    }
    onHarvested?.();
  };

  return (
    <ul className="space-y-1" data-testid="harvest-row">
      {offers.map((offer) => (
        <li
          key={`${offer.substance_id}-${offer.opponent_id ?? 'place'}`}
          className="flex items-center justify-between gap-2 text-xs"
        >
          <span>
            {primumName(offer.substance_name)}
            {offer.step_name && ` · ${offer.step_name}`}
            {offer.opponent_id !== null && ` · ${offer.opponent_name}`}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-6 shrink-0 px-2 text-xs"
            disabled={dispatch.isPending}
            onClick={() => void harvest(offer)}
          >
            Harvest
          </Button>
        </li>
      ))}
    </ul>
  );
}
