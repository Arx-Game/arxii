import { apiFetch } from '@/evennia_replacements/api';

import type { BattleDetail, PaginatedBattleListList } from './types';

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
