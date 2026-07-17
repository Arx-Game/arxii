import { apiFetch } from '@/evennia_replacements/api';

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
 * Result of a REGISTRY dispatch. `success` mirrors `DispatchResultSerializer`
 * (`src/actions/serializers.py:270-275`): the view always returns HTTP 200 for
 * a business-rule refusal, so `success === false` is the wire signal callers
 * must check to distinguish an honest failure from a real success — `null`
 * means the backend detail wasn't an `ActionResult` (not expected for the
 * REGISTRY-backed builder actions this dispatches, but treated as success so
 * a null never silently swallows a real failure toast).
 */
export interface DispatchResult {
  message: string;
  success: boolean | null;
}

/**
 * Dispatch a Room Builder REGISTRY action for `characterId` (the #1470
 * `editRoom` shape, generalized). Kwargs carry the explicit `room_id`
 * anchor so the canvas can operate building-wide. Returns the action's
 * human-readable result message plus its `success` flag; throws with the
 * server `detail` on 4xx.
 */
export async function dispatchRoomBuilder(
  characterId: number,
  registryKey: RoomBuilderActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: { backend: 'registry', registry_key: registryKey }, kwargs }),
  });
  if (!res.ok) {
    let detail = 'The action failed.';
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
  const data = (await res.json()) as { message?: string | null; success?: boolean | null };
  return { message: data.message ?? 'Done.', success: data.success ?? null };
}
