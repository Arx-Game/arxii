import { apiFetch } from '@/evennia_replacements/api';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

import type {
  PaginatedStoryAreaList,
  StoryArea,
  StoryAreaManager,
  StoryBuilderActionKey,
  StoryInstance,
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

export interface StoryAreaListParams {
  /** `has_parent=false` fetches root areas; omit to fetch every owned area (page 1). */
  hasParent?: boolean;
  /** `parent=<id>` fetches one area's direct children. */
  parent?: number;
}

/** A GM's own story areas (staff: every story area). Reads only — see `world.gm.story_views`. */
export function fetchStoryAreas(params: StoryAreaListParams = {}): Promise<PaginatedStoryAreaList> {
  const search = new URLSearchParams();
  if (params.hasParent !== undefined) search.set('has_parent', String(params.hasParent));
  if (params.parent !== undefined) search.set('parent', String(params.parent));
  const qs = search.toString();
  return getJson(`/api/gm/story-areas/${qs ? `?${qs}` : ''}`, 'Failed to load story areas.');
}

export function fetchStoryArea(areaId: number): Promise<StoryArea> {
  return getJson(`/api/gm/story-areas/${areaId}/`, 'Failed to load the story area.');
}

export function fetchStoryAreaManager(areaId: number): Promise<StoryAreaManager> {
  return getJson(`/api/gm/story-areas/${areaId}/manager/`, 'Failed to load the story area map.');
}

/**
 * A GM's own active temp scene rooms (staff: every GM-owned active instance).
 * A bare array — the endpoint's `pagination_class=None` (see `world.gm.story_views`)
 * because a GM has at most a handful of active temp rooms at once.
 */
export function fetchStoryInstances(): Promise<StoryInstance[]> {
  return getJson('/api/gm/story-areas/instances/', 'Failed to load temp scene rooms.');
}

/**
 * Dispatch a GM story-builder REGISTRY action (#2450 Tasks 5-7 keys) for
 * `characterId`. Thin wrapper pinning `StoryBuilderActionKey` over the
 * shared `dispatchCanvasAction` (`@/map-canvas/dispatch`) — same wire shape
 * as `dispatchWorldBuilder` (`frontend/src/world-builder/api.ts`), different
 * key union.
 */
export function dispatchStoryBuilder(
  characterId: number,
  registryKey: StoryBuilderActionKey,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, registryKey, kwargs);
}
