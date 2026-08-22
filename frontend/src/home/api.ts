/**
 * Landing page (Gatefold) API functions — public "shop-window" reads (#3305).
 *
 * Every endpoint here is deliberately safe for anonymous visitors: content is
 * gated by trust-level filtering / query scoping server-side (see
 * `StartingAreaViewSet`/`BeginningsViewSet`/`InteractionViewSet.get_permissions`),
 * not by authentication. Types are reused from the modules that already own
 * these shapes (`character-creation`, `scenes`) rather than re-declared here.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { Beginnings, StartingArea } from '@/character-creation/types';
import type { Interaction, SceneListItem } from '@/scenes/types';

/** `GET /api/scenes/spotlight/` response shape (`ScenesSpotlightSerializer`). */
export interface ScenesSpotlightData {
  in_progress: SceneListItem[];
  recent: SceneListItem[];
}

/** Cursor-paginated envelope `GET /api/interactions/` returns. */
interface PaginatedInteractions {
  results: Interaction[];
}

export async function getPublicStartingAreas(): Promise<StartingArea[]> {
  const res = await apiFetch('/api/character-creation/starting-areas/');
  if (!res.ok) {
    throw new Error('Failed to load starting areas');
  }
  return res.json();
}

export async function getPublicBeginnings(startingAreaId: number): Promise<Beginnings[]> {
  const res = await apiFetch(`/api/character-creation/beginnings/?starting_area=${startingAreaId}`);
  if (!res.ok) {
    throw new Error('Failed to load beginnings');
  }
  return res.json();
}

export async function getScenesSpotlight(): Promise<ScenesSpotlightData> {
  const res = await apiFetch('/api/scenes/spotlight/');
  if (!res.ok) {
    throw new Error('Failed to load scenes spotlight');
  }
  return res.json();
}

/** Latest interactions for one scene (newest first — `InteractionCursorPagination.ordering`). */
export async function getSceneInteractions(sceneId: number): Promise<Interaction[]> {
  const res = await apiFetch(`/api/interactions/?scene=${sceneId}`);
  if (!res.ok) {
    throw new Error('Failed to load scene interactions');
  }
  const data: PaginatedInteractions = await res.json();
  return data.results;
}

/** Count of scenes matching `status=completed&finished_after=<ISO timestamp>`. */
export async function getCompletedSceneCount(finishedAfter: string): Promise<number> {
  const res = await apiFetch(
    `/api/scenes/?status=completed&finished_after=${encodeURIComponent(finishedAfter)}`
  );
  if (!res.ok) {
    throw new Error('Failed to load scene count');
  }
  const data: { count: number } = await res.json();
  return data.count;
}
