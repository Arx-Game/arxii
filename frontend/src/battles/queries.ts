import { useQuery } from '@tanstack/react-query';

import { fetchBattleDetail, fetchBattlesForScene } from './api';

export const battleKeys = {
  all: ['battles'] as const,
  detail: (battleId: number) => [...battleKeys.all, 'detail', battleId] as const,
  forScene: (sceneId: number) => [...battleKeys.all, 'for-scene', sceneId] as const,
};

/**
 * A Scene has at most one Battle (1:1 extension, world/battles/models.py) — this
 * lists with `?scene=` and hands back the first result (or null) so callers get
 * the single-battle shape they actually need.
 */
export function useBattleForSceneQuery(sceneId: number | null | undefined) {
  return useQuery({
    queryKey: battleKeys.forScene(sceneId ?? 0),
    queryFn: async () => {
      const data = await fetchBattlesForScene(sceneId!);
      return data.results[0] ?? null;
    },
    enabled: sceneId != null,
    staleTime: 30_000,
  });
}

export function useBattleDetailQuery(battleId: number | null | undefined) {
  return useQuery({
    queryKey: battleKeys.detail(battleId ?? 0),
    queryFn: () => fetchBattleDetail(battleId!),
    enabled: battleId != null,
    staleTime: 15_000,
  });
}
