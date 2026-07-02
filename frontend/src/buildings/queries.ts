import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  dispatchRoomBuilder,
  fetchBuildingForRoom,
  fetchBuildingManager,
  fetchDecorationTemplates,
  fetchRoomComfort,
  fetchRoomSizeTiers,
  searchPersonas,
} from './api';
import type { RoomBuilderActionKey } from './types';

const FIVE_MINUTES = 5 * 60 * 1000;

export const buildingKeys = {
  all: ['buildings'] as const,
  manager: (buildingId: number) => [...buildingKeys.all, 'manager', buildingId] as const,
  forRoom: (roomId: number) => [...buildingKeys.all, 'for-room', roomId] as const,
  roomComfort: (roomId: number) => [...buildingKeys.all, 'room-comfort', roomId] as const,
  sizeTiers: () => [...buildingKeys.all, 'room-size-tiers'] as const,
  templates: (search: string) => [...buildingKeys.all, 'decoration-templates', search] as const,
  personaSearch: (term: string) => [...buildingKeys.all, 'persona-search', term] as const,
};

export function useBuildingManagerQuery(
  buildingId: number | null | undefined,
  characterId: number | null | undefined
) {
  return useQuery({
    queryKey: buildingKeys.manager(buildingId ?? 0),
    queryFn: () => fetchBuildingManager(buildingId!, characterId!),
    enabled: buildingId != null && characterId != null,
    staleTime: 30_000,
  });
}

export function useBuildingForRoomQuery(
  roomId: number | null | undefined,
  characterId: number | null | undefined
) {
  return useQuery({
    queryKey: buildingKeys.forRoom(roomId ?? 0),
    queryFn: () => fetchBuildingForRoom(roomId!, characterId!),
    enabled: roomId != null && characterId != null,
    staleTime: 30_000,
  });
}

export function useRoomComfortQuery(
  roomId: number | null | undefined,
  characterId: number | null | undefined
) {
  return useQuery({
    queryKey: buildingKeys.roomComfort(roomId ?? 0),
    queryFn: () => fetchRoomComfort(roomId!, characterId!),
    enabled: roomId != null && characterId != null,
    staleTime: 15_000,
  });
}

export function useRoomSizeTiersQuery(enabled = true) {
  return useQuery({
    queryKey: buildingKeys.sizeTiers(),
    queryFn: fetchRoomSizeTiers,
    enabled,
    staleTime: FIVE_MINUTES,
  });
}

export function useDecorationTemplatesQuery(search = '', enabled = true) {
  return useQuery({
    queryKey: buildingKeys.templates(search),
    queryFn: () => fetchDecorationTemplates(search || undefined),
    enabled,
    staleTime: FIVE_MINUTES,
  });
}

export function usePersonaSearchQuery(term: string) {
  return useQuery({
    queryKey: buildingKeys.personaSearch(term),
    queryFn: () => searchPersonas(term),
    enabled: term.trim().length >= 2,
    staleTime: 30_000,
  });
}

export interface RoomBuilderActionInput {
  key: RoomBuilderActionKey;
  kwargs: Record<string, unknown>;
}

/**
 * The one mutation every builder verb goes through: dispatch by registry
 * key, toast the action's message, refresh the manager payload.
 */
export function useRoomBuilderAction(characterId: number, buildingId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, kwargs }: RoomBuilderActionInput) =>
      dispatchRoomBuilder(characterId, key, kwargs),
    onSuccess: (message: string) => {
      toast.success(message);
      if (buildingId != null) {
        void queryClient.invalidateQueries({ queryKey: buildingKeys.manager(buildingId) });
      }
      void queryClient.invalidateQueries({ queryKey: [...buildingKeys.all, 'room-comfort'] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}
