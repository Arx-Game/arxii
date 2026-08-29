/**
 * The Hall (#3412 slice 2) — React Query hooks for surfaces with no existing
 * home. Invitation/offer *response* mutations and their list fetches mostly
 * live in their owning domains (`@/events/queries`, `@/societies/queries`)
 * and are re-exported/composed by the band components directly — this file
 * is only for what's genuinely new here: the clock.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchClockState } from './api';
import { useAccount } from '@/store/hooks';

export const hallKeys = {
  clock: ['hall', 'clock'] as const,
};

const ONE_MINUTE = 60 * 1000;

/** The World band's calendar plate. No `throwOnError` — a clock hiccup shouldn't blank the Hall. */
export function useClockQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: hallKeys.clock,
    queryFn: fetchClockState,
    enabled: !!account,
    staleTime: ONE_MINUTE,
  });
}
