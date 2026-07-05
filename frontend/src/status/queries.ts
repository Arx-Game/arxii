/**
 * Status React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchActionPoints, fetchCharacterPurse } from './api';
import type { ActionPointPool, CharacterPurse } from './api';

/** The viewer's coin purse for a character. Disabled when characterId <= 0. */
export function useCharacterPurse(characterId: number) {
  return useQuery<CharacterPurse | null>({
    queryKey: ['status', 'purse', characterId],
    queryFn: () => fetchCharacterPurse(characterId),
    enabled: characterId > 0,
    staleTime: 10_000,
  });
}

/** The viewer's AP pool for a character. Disabled when characterId <= 0. */
export function useActionPoints(characterId: number) {
  return useQuery<ActionPointPool | null>({
    queryKey: ['status', 'action-points', characterId],
    queryFn: () => fetchActionPoints(characterId),
    enabled: characterId > 0,
    staleTime: 10_000,
  });
}
