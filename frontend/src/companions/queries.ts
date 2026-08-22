/**
 * Companion React Query hooks (#3294).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchMyCompanions } from './api';

export const companionKeys = {
  all: ['companions'] as const,
  mine: () => [...companionKeys.all, 'mine'] as const,
};

/**
 * The viewer's own active character's bonded companions — backs the composer's
 * `CompanionSelector` (#3294), which further narrows to `is_present` entries.
 * Self-scoped server-side (no character param needed); an account with no
 * active character gets an empty array, never an error.
 */
export function useMyCompanions() {
  return useQuery({
    queryKey: companionKeys.mine(),
    queryFn: fetchMyCompanions,
  });
}
