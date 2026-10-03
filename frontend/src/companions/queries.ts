/**
 * Companion React Query hooks (#3294).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchCompanionArchetypes, fetchMyCompanions } from './api';

export const companionKeys = {
  all: ['companions'] as const,
  mine: () => [...companionKeys.all, 'mine'] as const,
  archetypes: () => [...companionKeys.all, 'archetypes'] as const,
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

/** The authored CompanionArchetype catalog (#4091) — backs the
 * Bind-as-companion archetype picker on WonOverRows. Static reference data;
 * a long staleTime avoids refetching it every time the form opens. `enabled`
 * lets a caller defer the fetch until the form is actually open. */
export function useCompanionArchetypes(enabled = true) {
  return useQuery({
    queryKey: companionKeys.archetypes(),
    queryFn: fetchCompanionArchetypes,
    staleTime: 5 * 60_000,
    enabled,
  });
}
