/**
 * Dreams React Query hooks (#3003).
 */

import { useQuery } from '@tanstack/react-query';
import { getDreamState } from './api';

export const dreamKeys = {
  all: ['dreams'] as const,
  state: (characterId: number) => [...dreamKeys.all, 'state', characterId] as const,
};

/**
 * The dreamspace panel's one read: everything needed for the play-view
 * takeover (room, co-dreamers, dreamwalk candidates, wake/descend/ascend
 * availability). `characterId <= 0` (no active puppet resolved yet) leaves
 * the query disabled rather than firing a request that can't resolve.
 */
export function useDreamState(characterId: number) {
  return useQuery({
    queryKey: dreamKeys.state(characterId),
    queryFn: () => getDreamState(characterId),
    enabled: characterId > 0,
  });
}
