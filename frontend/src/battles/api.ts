import { apiFetch } from '@/evennia_replacements/api';

import type {
  BattleDetail,
  PaginatedBattleListList,
  PaginatedBattleMapBlueprintList,
  PaginatedBattleUnitTemplateList,
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

export function fetchBattlesForScene(sceneId: number): Promise<PaginatedBattleListList> {
  return getJson(`/api/battles/?scene=${sceneId}`, 'Failed to load the battle.');
}

export function fetchBattleDetail(battleId: number): Promise<BattleDetail> {
  return getJson(`/api/battles/${battleId}/`, 'Failed to load the battle.');
}

/**
 * GM staging catalogs (#2010, Task 5) — active-only, page_size=100 since
 * these back a picker `<select>`, not a browsable/paginated list UI.
 */
export function fetchBattleMapBlueprints(): Promise<PaginatedBattleMapBlueprintList> {
  return getJson(
    '/api/battles/map-blueprints/?is_active=true&page_size=100',
    'Failed to load battle-map blueprints.'
  );
}

export function fetchBattleUnitTemplates(): Promise<PaginatedBattleUnitTemplateList> {
  return getJson(
    '/api/battles/unit-templates/?is_active=true&page_size=100',
    'Failed to load battle-unit templates.'
  );
}
