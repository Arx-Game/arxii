/**
 * Comfort React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchCharacterComfort } from './api';

/**
 * The active character's personal comfort readout. Disabled until a character is known.
 * Re-polls each minute so a fresh weather roll (or a change of clothes) stays current.
 */
export function useCharacterComfort(characterId: number | null) {
  return useQuery({
    queryKey: ['comfort', 'summary', characterId],
    queryFn: () => fetchCharacterComfort(characterId as number),
    enabled: characterId != null,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
