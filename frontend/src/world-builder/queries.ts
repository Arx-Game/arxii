import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  dispatchWorldBuilder,
  fetchAreaManager,
  fetchWorldBuilderArea,
  fetchWorldBuilderAreas,
  type AreaListParams,
} from './api';
import type { WorldBuilderActionKey } from './types';

/** Hierarchical key namespace with matchable prefixes (project convention). */
export const worldBuilderKeys = {
  all: ['world-builder'] as const,
  areas: (params: AreaListParams = {}) => [...worldBuilderKeys.all, 'areas', params] as const,
  area: (areaId: number) => [...worldBuilderKeys.all, 'area', areaId] as const,
  manager: (areaId: number) => [...worldBuilderKeys.all, 'manager', areaId] as const,
};

export function useWorldBuilderAreasQuery(params: AreaListParams = {}, enabled = true) {
  return useQuery({
    queryKey: worldBuilderKeys.areas(params),
    queryFn: () => fetchWorldBuilderAreas(params),
    enabled,
    staleTime: 30_000,
  });
}

export function useWorldBuilderAreaQuery(areaId: number | null | undefined) {
  return useQuery({
    queryKey: worldBuilderKeys.area(areaId ?? 0),
    queryFn: () => fetchWorldBuilderArea(areaId!),
    enabled: areaId != null,
    staleTime: 30_000,
  });
}

export function useAreaManagerQuery(areaId: number | null | undefined) {
  return useQuery({
    queryKey: worldBuilderKeys.manager(areaId ?? 0),
    queryFn: () => fetchAreaManager(areaId!),
    enabled: areaId != null,
    staleTime: 15_000,
  });
}

export interface WorldBuilderActionInput {
  key: WorldBuilderActionKey;
  kwargs: Record<string, unknown>;
}

/** Actions that reshape the area tree itself, not just one area's manager payload. */
const AREA_TREE_KEYS: WorldBuilderActionKey[] = ['create_area', 'edit_area', 'promote_area'];

/**
 * The one mutation every staff world-builder verb goes through: dispatch by
 * registry key, toast the action's message, refresh the area manager payload
 * (pattern: `buildings/queries.ts:126-142`). Area-tree-shaping actions
 * additionally invalidate the areas list/detail — the key factory's
 * `['world-builder', 'areas']` prefix matches every cached params variant.
 * A `success: false` dispatch (a business-rule refusal — HTTP 200, see
 * `DispatchResult` in `./api`) toasts an error and skips every cache
 * invalidation instead, so a refused action never looks like it landed.
 */
export function useWorldBuilderAction(characterId: number, areaId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, kwargs }: WorldBuilderActionInput) =>
      dispatchWorldBuilder(characterId, key, kwargs),
    onSuccess: ({ message, success }, { key }) => {
      if (success === false) {
        toast.error(message);
        return;
      }
      toast.success(message);
      if (areaId != null) {
        queryClient.invalidateQueries({ queryKey: worldBuilderKeys.manager(areaId) });
      }
      if (AREA_TREE_KEYS.includes(key)) {
        queryClient.invalidateQueries({ queryKey: [...worldBuilderKeys.all, 'areas'] });
        queryClient.invalidateQueries({ queryKey: [...worldBuilderKeys.all, 'area'] });
      }
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}
