import { useQuery } from '@tanstack/react-query';

import {
  fetchBattleDetail,
  fetchBattleMapBlueprints,
  fetchBattlesForScene,
  fetchBattleUnitTemplates,
} from './api';

export const battleKeys = {
  all: ['battles'] as const,
  detail: (battleId: number) => [...battleKeys.all, 'detail', battleId] as const,
  forScene: (sceneId: number) => [...battleKeys.all, 'for-scene', sceneId] as const,
  mapBlueprints: () => [...battleKeys.all, 'map-blueprints'] as const,
  unitTemplates: () => [...battleKeys.all, 'unit-templates'] as const,
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
    // Staging is multi-GM: poll so another GM's changes appear without a reload (#2423).
    refetchInterval: 10_000,
    staleTime: 15_000,
  });
}

/**
 * GM staging catalogs (#2010) — active blueprints/templates for StagingPanel's
 * pickers. `enabled` lets the panel skip the fetch until the corresponding
 * staging action (create_battle/stage_battle_map/spawn_battle_units) is
 * actually present in the viewer's available-actions list.
 */
export function useBattleMapBlueprintsQuery(enabled = true) {
  return useQuery({
    queryKey: battleKeys.mapBlueprints(),
    queryFn: fetchBattleMapBlueprints,
    enabled,
    staleTime: 60_000,
  });
}

export function useBattleUnitTemplatesQuery(enabled = true) {
  return useQuery({
    queryKey: battleKeys.unitTemplates(),
    queryFn: fetchBattleUnitTemplates,
    enabled,
    staleTime: 60_000,
  });
}
