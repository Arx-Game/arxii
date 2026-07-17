import { apiFetch } from '@/evennia_replacements/api';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type {
  BuildingManagerPayload,
  ForRoomResult,
  PaginatedArchitecturalStyleList,
  PaginatedBuildingKindList,
  PaginatedDecorationTemplateList,
  PaginatedRoomSizeTierList,
  RoomBuilderActionKey,
  RoomComfortBreakdown,
} from './types';

export type { DispatchResult };

async function getJson<T>(url: string, fallbackError: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) {
    let detail = fallbackError;
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // body wasn't JSON; keep the generic message
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function fetchBuildingManager(
  buildingId: number,
  characterId: number
): Promise<BuildingManagerPayload> {
  return getJson(
    `/api/buildings/manager/${buildingId}/?character_id=${characterId}`,
    'Failed to load the building.'
  );
}

export function fetchBuildingForRoom(roomId: number, characterId: number): Promise<ForRoomResult> {
  return getJson(
    `/api/buildings/manager/for-room/${roomId}/?character_id=${characterId}`,
    'Failed to resolve the building.'
  );
}

export function fetchRoomComfort(
  roomId: number,
  characterId: number
): Promise<RoomComfortBreakdown> {
  return getJson(
    `/api/buildings/manager/room/${roomId}/comfort/?character_id=${characterId}`,
    'Failed to load the comfort readout.'
  );
}

export function fetchRoomSizeTiers(): Promise<PaginatedRoomSizeTierList> {
  return getJson('/api/buildings/room-size-tiers/', 'Failed to load room sizes.');
}

export function fetchDecorationTemplates(
  search?: string
): Promise<PaginatedDecorationTemplateList> {
  const params = search ? `?search=${encodeURIComponent(search)}` : '';
  return getJson(
    `/api/buildings/decoration-templates/${params}`,
    'Failed to load the decoration catalog.'
  );
}

export function fetchBuildingKinds(search?: string): Promise<PaginatedBuildingKindList> {
  const params = search ? `?search=${encodeURIComponent(search)}` : '';
  return getJson(`/api/buildings/building-kinds/${params}`, 'Failed to load building kinds.');
}

export function fetchArchitecturalStyles(
  characterId: number,
  search?: string
): Promise<PaginatedArchitecturalStyleList> {
  const params = new URLSearchParams({ character_id: String(characterId) });
  if (search) params.set('search', search);
  return getJson(
    `/api/buildings/architectural-styles/?${params.toString()}`,
    'Failed to load architectural styles.'
  );
}

export interface PersonaSearchResult {
  id: number;
  name: string;
}

/** Search personas by name for the assign-tenant picker (PersonaViewSet search). */
export async function searchPersonas(term: string): Promise<PersonaSearchResult[]> {
  const data = await getJson<{ results: PersonaSearchResult[] }>(
    `/api/scenes/personas/?search=${encodeURIComponent(term)}`,
    'Persona search failed.'
  );
  return data.results;
}

/**
 * Dispatch a Room Builder REGISTRY action for `characterId` (the #1470
 * `editRoom` shape, generalized). Kwargs carry the explicit `room_id`
 * anchor so the canvas can operate building-wide. Thin wrapper pinning
 * `RoomBuilderActionKey` over the shared `dispatchCanvasAction`
 * (`@/map-canvas/dispatch`).
 */
export function dispatchRoomBuilder(
  characterId: number,
  registryKey: RoomBuilderActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, registryKey, kwargs);
}
