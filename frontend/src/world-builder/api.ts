import { apiFetch, withQuery } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type {
  PaginatedWorldBuilderAreaList,
  WorldBuilderActionKey,
  WorldBuilderArea,
  WorldBuilderAreaManager,
  WorldBuilderRoomDetail,
  WorldBuilderRoomHit,
} from './types';

export type { DispatchResult };

async function getJson<T>(url: string, fallbackError: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) await throwApiError(res, fallbackError);
  return (await res.json()) as T;
}

export interface AreaListParams {
  /** `has_parent=false` fetches root areas; omit to fetch every area (page 1). */
  hasParent?: boolean;
  /** `parent=<id>` fetches one area's direct children. */
  parent?: number;
}

export function fetchWorldBuilderAreas(
  params: AreaListParams = {}
): Promise<PaginatedWorldBuilderAreaList> {
  const search = new URLSearchParams();
  if (params.hasParent !== undefined) search.set('has_parent', String(params.hasParent));
  if (params.parent !== undefined) search.set('parent', String(params.parent));
  const qs = search.toString();
  return getJson(withQuery(`/api/world-builder/areas/`, qs), 'Failed to load areas.');
}

export function fetchWorldBuilderArea(areaId: number): Promise<WorldBuilderArea> {
  return getJson(`/api/world-builder/areas/${areaId}/`, 'Failed to load the area.');
}

export function fetchAreaManager(areaId: number): Promise<WorldBuilderAreaManager> {
  return getJson(`/api/world-builder/areas/${areaId}/manager/`, 'Failed to load the area map.');
}

/** Selection-time room detail (#3269): exit profiles, comfort, ambient rows. */
export function fetchRoomDetail(roomId: number): Promise<WorldBuilderRoomDetail> {
  const qs = new URLSearchParams({ room_id: String(roomId) }).toString();
  return getJson(`/api/world-builder/areas/room-detail/?${qs}`, 'Failed to load room detail.');
}

/** Cross-area room search (#3269): matches room key or fixture key, capped at 50. */
export function searchWorldBuilderRooms(term: string): Promise<WorldBuilderRoomHit[]> {
  const qs = new URLSearchParams({ search: term }).toString();
  return getJson(`/api/world-builder/areas/room-search/?${qs}`, 'Room search failed.');
}

/**
 * Dispatch a staff world-builder REGISTRY action (#2449 Task 3 keys) for
 * `characterId`. Thin wrapper pinning `WorldBuilderActionKey` over the
 * shared `dispatchCanvasAction` (`@/map-canvas/dispatch`) — same wire shape
 * as `dispatchRoomBuilder` (`frontend/src/buildings/api.ts`), different key
 * union.
 */
export function dispatchWorldBuilder(
  characterId: number,
  registryKey: WorldBuilderActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, registryKey, kwargs);
}
