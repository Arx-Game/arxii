import { apiFetch } from '@/evennia_replacements/api';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type {
  PaginatedWorldBuilderAreaList,
  WorldBuilderActionKey,
  WorldBuilderArea,
  WorldBuilderAreaManager,
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
  return getJson(`/api/world-builder/areas/${qs ? `?${qs}` : ''}`, 'Failed to load areas.');
}

export function fetchWorldBuilderArea(areaId: number): Promise<WorldBuilderArea> {
  return getJson(`/api/world-builder/areas/${areaId}/`, 'Failed to load the area.');
}

export function fetchAreaManager(areaId: number): Promise<WorldBuilderAreaManager> {
  return getJson(`/api/world-builder/areas/${areaId}/manager/`, 'Failed to load the area map.');
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
