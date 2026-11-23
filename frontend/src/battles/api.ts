import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

import type {
  BattleDetail,
  PaginatedBattleListList,
  PaginatedBattleMapBlueprintList,
  PaginatedBattleUnitTemplateList,
} from './types';

async function getJson<T>(
  url: string,
  fallbackError: string,
  headers: Record<string, string> = {}
): Promise<T> {
  const res = await apiFetch(url, { headers });
  if (!res.ok) await throwApiError(res, fallbackError);
  return (await res.json()) as T;
}

/**
 * The character this tab plays, sent as `X-Character-ID` (`web.api.mixins.CharacterContextMixin`).
 * The battle roster marks only that character's row `is_mine`; it carries no sheet ids (#5290).
 */
function characterHeaders(characterId: number | null): Record<string, string> {
  return characterId === null ? {} : { 'X-Character-ID': String(characterId) };
}

export function fetchBattlesForScene(
  sceneId: number,
  characterId: number | null
): Promise<PaginatedBattleListList> {
  return getJson(
    `/api/battles/?scene=${sceneId}`,
    'Failed to load the battle.',
    characterHeaders(characterId)
  );
}

export function fetchBattleDetail(
  battleId: number,
  characterId: number | null
): Promise<BattleDetail> {
  return getJson(
    `/api/battles/${battleId}/`,
    'Failed to load the battle.',
    characterHeaders(characterId)
  );
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
