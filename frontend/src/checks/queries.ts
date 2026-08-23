/**
 * React Query hooks for scene check invocation (#3295).
 */

import { useQuery } from '@tanstack/react-query';
import * as api from './api';

export const sceneCheckKeys = {
  all: ['scene-checks'] as const,
  playerCheckTypes: (search: string, characterId: number | null) =>
    [...sceneCheckKeys.all, 'player-check-types', search, characterId] as const,
  myCheckCalls: () => [...sceneCheckKeys.all, 'my-check-calls'] as const,
};

/** Enabled only while the picker is open — mirrors `useCheckTypeCatalog`. */
export function usePlayerCheckTypeCatalog(
  search: string,
  characterId: number | null,
  enabled: boolean
) {
  return useQuery({
    queryKey: sceneCheckKeys.playerCheckTypes(search, characterId),
    queryFn: () => api.getPlayerCheckTypeCatalog(search, characterId),
    enabled,
    staleTime: 30_000,
  });
}

/**
 * Poll the requesting player's pending check-call prompt(s) (#3295).
 * Mirrors `useSummonOfferInbox` — 15s poll so an incoming call appears
 * without a manual refresh.
 */
export function useMyCheckCalls(options: { enabled?: boolean } = {}) {
  const { enabled = true } = options;
  return useQuery({
    queryKey: sceneCheckKeys.myCheckCalls(),
    queryFn: () => api.fetchMyCheckCalls(),
    enabled,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}
