/**
 * Almanach de Catenys API (#3983 Task 7): the staff house-builder reads plus
 * REGISTRY dispatch, following `world-builder/api.ts` line for line in shape
 * — `apiFetch`/`withQuery` for GET, `throwApiError` on a non-ok response,
 * and the shared `dispatchCanvasAction` for the ten REGISTRY actions Task 6
 * wired. Every route here is staff-only (`IsAdminUser`, `almanach_views.py`).
 */
import { apiFetch, withQuery } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type {
  AlmanachActionKey,
  HouseDocument,
  LadderMode,
  LadderPayload,
  PaginatedAlmanachHouseSummaryList,
  PaginatedAlmanachRealmList,
  PaginatedLandShapeList,
} from './types';

export type { DispatchResult };

async function getJson<T>(url: string, fallbackError: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) await throwApiError(res, fallbackError);
  return (await res.json()) as T;
}

export function fetchRealms(): Promise<PaginatedAlmanachRealmList> {
  return getJson('/api/almanach/realms/', 'Failed to load realms.');
}

/** `?for=staff|founder` — NOTE the wire param is `for`, not `mode`. */
export function fetchLadder(realmId: number, mode: LadderMode): Promise<LadderPayload> {
  const qs = new URLSearchParams({ for: mode }).toString();
  return getJson(
    withQuery(`/api/almanach/realms/${realmId}/ladder/`, qs),
    'Failed to load the ladder.'
  );
}

export function fetchHouses(realmId: number): Promise<PaginatedAlmanachHouseSummaryList> {
  const qs = new URLSearchParams({ realm: String(realmId) }).toString();
  return getJson(withQuery('/api/almanach/houses/', qs), 'Failed to load houses.');
}

export function fetchHouseDocument(houseId: number): Promise<HouseDocument> {
  return getJson(`/api/almanach/houses/${houseId}/document/`, 'Failed to load the house document.');
}

export function fetchLandShapes(): Promise<PaginatedLandShapeList> {
  return getJson('/api/almanach/land-shapes/', 'Failed to load land shapes.');
}

/**
 * Dispatch a staff Almanach REGISTRY action (#3983 Task 6 keys) for
 * `characterId`. Thin wrapper pinning `AlmanachActionKey` over the shared
 * `dispatchCanvasAction` (`@/map-canvas/dispatch`) — same wire shape as
 * `dispatchWorldBuilder` (`@/world-builder/api`), different key union.
 */
export function dispatchAlmanach(
  characterId: number,
  key: AlmanachActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, key, kwargs);
}
