import { toast } from 'sonner';
import type { KudosReceivedPayload } from './types';
import { queryClient } from '@/queryClient';

/**
 * kudos_received (#2161) — fired from `notify_kudos_received` on every kudos
 * award (pose chip, writeup commend, weekly engagement, spread-assist), so
 * applause surfaces in-context instead of requiring a trip to the progression
 * page. Anonymous by design (ADR-0033): the payload carries no giver identity.
 *
 * A quiet toast (never `toast.error`) plus an `account-progression`
 * invalidation so the recipient's kudos/XP totals refresh without a reload.
 */
export function handleKudosReceivedPayload(payload: KudosReceivedPayload | undefined) {
  const {
    amount,
    source_category: sourceCategory,
    description,
  } = payload ?? {
    amount: 0,
    source_category: '',
    description: '',
  };
  toast(`+${amount} kudos — ${description}`, { description: sourceCategory });
  queryClient.invalidateQueries({ queryKey: ['account-progression'] });
}
