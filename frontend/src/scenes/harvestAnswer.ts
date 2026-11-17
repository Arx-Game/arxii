/**
 * What pressing Harvest came to (#5125): the server's one sentence, plus the sentence on what
 * the source holds now when it sends one. The caller holds it, so it stays on screen after the
 * lair empties or the foe stops being offered.
 */
import type { HarvestOffer } from '@/hooks/types';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';

export interface HarvestAnswer {
  success: boolean;
  message: string;
  remainingLine: string;
}

export async function runHarvest(
  dispatch: (body: DispatchActionRequest) => Promise<DispatchResult>,
  offer: HarvestOffer
): Promise<HarvestAnswer> {
  try {
    const result = await dispatch({
      ref: { backend: 'registry', registry_key: 'harvest_primum' },
      kwargs: { substance: offer.substance_id, opponent_id: offer.opponent_id },
    });
    const data = (result.data ?? {}) as { remaining_line?: string };
    return {
      success: !isDispatchFailure(result),
      message: result.message ?? 'You could not extract it.',
      remainingLine: data.remaining_line ?? '',
    };
  } catch (err) {
    return {
      success: false,
      message: err instanceof Error ? err.message : 'You could not extract it.',
      remainingLine: '',
    };
  }
}

/** "fire" -> "Fire Primum". */
export function primumName(substanceName: string): string {
  return `${substanceName.charAt(0).toUpperCase()}${substanceName.slice(1)} Primum`;
}

/** "Fire Primum · Massive": a substance's Primum and the step it reads at. */
export function offerLabel(offer: HarvestOffer): string {
  const name = primumName(offer.substance_name);
  return offer.step_name ? `${name} · ${offer.step_name}` : name;
}

/**
 * "Check: Harvest Primum · +2 from your thread on Pyromancy": the check she rolls, with the
 * bonus her thread on the matching Gift adds when she has one. Empty while no check is set.
 */
export function checkLine(offer: HarvestOffer | undefined): string {
  if (!offer?.check_name) {
    return '';
  }
  const bonus = offer.thread_bonus ?? 0;
  return bonus > 0
    ? `Check: ${offer.check_name} · +${bonus} from your thread on ${offer.thread_gift_name}`
    : `Check: ${offer.check_name}`;
}
