import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  dispatchStoryBuilder,
  fetchStoryArea,
  fetchStoryAreaManager,
  fetchStoryAreas,
  fetchStoryInstances,
  type StoryAreaListParams,
} from './api';
import type { StoryBuilderActionKey } from './types';

/** Hierarchical key namespace with matchable prefixes (project convention). */
export const storyBuilderKeys = {
  all: ['story-builder'] as const,
  areas: (params: StoryAreaListParams = {}) => [...storyBuilderKeys.all, 'areas', params] as const,
  area: (areaId: number) => [...storyBuilderKeys.all, 'area', areaId] as const,
  manager: (areaId: number) => [...storyBuilderKeys.all, 'manager', areaId] as const,
  instances: () => [...storyBuilderKeys.all, 'instances'] as const,
};

export function useStoryAreasQuery(params: StoryAreaListParams = {}, enabled = true) {
  return useQuery({
    queryKey: storyBuilderKeys.areas(params),
    queryFn: () => fetchStoryAreas(params),
    enabled,
    staleTime: 30_000,
  });
}

export function useStoryAreaQuery(areaId: number | null | undefined) {
  return useQuery({
    queryKey: storyBuilderKeys.area(areaId ?? 0),
    queryFn: () => fetchStoryArea(areaId!),
    enabled: areaId != null,
    staleTime: 30_000,
  });
}

export function useStoryAreaManagerQuery(areaId: number | null | undefined) {
  return useQuery({
    queryKey: storyBuilderKeys.manager(areaId ?? 0),
    queryFn: () => fetchStoryAreaManager(areaId!),
    enabled: areaId != null,
    staleTime: 15_000,
  });
}

export function useStoryInstancesQuery() {
  return useQuery({
    queryKey: storyBuilderKeys.instances(),
    queryFn: fetchStoryInstances,
    staleTime: 15_000,
  });
}

export interface StoryBuilderActionInput {
  key: StoryBuilderActionKey;
  kwargs: Record<string, unknown>;
}

/** Actions that reshape the area list itself, not just one area's manager payload. */
const AREA_LIST_KEYS: StoryBuilderActionKey[] = [
  'create_story_area',
  'edit_story_area',
  'remove_story_area',
];

/** Actions that reshape the GM's temp scene rooms list. */
const INSTANCE_KEYS: StoryBuilderActionKey[] = ['spin_up_scene_room', 'close_scene_room'];

/**
 * The one mutation every GM story-builder verb goes through: dispatch by
 * registry key, toast the action's message, refresh the area manager payload
 * (mirrors `useWorldBuilderAction`, `frontend/src/world-builder/queries.ts`).
 * Area-list-shaping actions additionally invalidate the areas list/detail;
 * temp-room actions invalidate the instances list. A `success: false`
 * dispatch (a business-rule refusal — HTTP 200, see `DispatchResult` in
 * `./api`) toasts an error and skips every cache invalidation instead, so a
 * refused action never looks like it landed.
 */
export function useStoryBuilderAction(characterId: number, areaId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, kwargs }: StoryBuilderActionInput) =>
      dispatchStoryBuilder(characterId, key, kwargs),
    onSuccess: ({ message, success }, { key }) => {
      if (success === false) {
        toast.error(message);
        return;
      }
      toast.success(message);
      if (areaId != null) {
        queryClient.invalidateQueries({ queryKey: storyBuilderKeys.manager(areaId) });
      }
      if (AREA_LIST_KEYS.includes(key)) {
        queryClient.invalidateQueries({ queryKey: [...storyBuilderKeys.all, 'areas'] });
        queryClient.invalidateQueries({ queryKey: [...storyBuilderKeys.all, 'area'] });
      }
      if (INSTANCE_KEYS.includes(key)) {
        queryClient.invalidateQueries({ queryKey: storyBuilderKeys.instances() });
      }
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}
