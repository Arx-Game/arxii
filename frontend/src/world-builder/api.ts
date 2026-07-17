import { apiFetch } from '@/evennia_replacements/api';

import type {
  PaginatedWorldBuilderAreaList,
  WorldBuilderActionKey,
  WorldBuilderArea,
  WorldBuilderAreaManager,
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
 * Result of a REGISTRY dispatch. `success` mirrors `DispatchResultSerializer`
 * (`src/actions/serializers.py:270-275`): the view always returns HTTP 200 for
 * a business-rule refusal, so `success === false` is the wire signal callers
 * must check to distinguish an honest failure from a real success — `null`
 * means the backend detail wasn't an `ActionResult` (not expected for the
 * REGISTRY-backed world-builder actions this dispatches, but treated as
 * success so a null never silently swallows a real failure toast).
 */
export interface DispatchResult {
  message: string;
  success: boolean | null;
}

/**
 * Dispatch a staff world-builder REGISTRY action (#2449 Task 3 keys) for
 * `characterId`. Mirrors `dispatchRoomBuilder`
 * (`frontend/src/buildings/api.ts:109-133`) — same wire shape, different key
 * union. Returns the action's human-readable result message plus its
 * `success` flag; throws with the server `detail` on 4xx.
 */
export async function dispatchWorldBuilder(
  characterId: number,
  registryKey: WorldBuilderActionKey,
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
