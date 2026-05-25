import { apiFetch } from '@/evennia_replacements/api';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

/**
 * Query key factory for scene queries.
 *
 * detail(id) produces ['scene', String(id)], which matches the legacy raw-array
 * shape used in SceneDetailPage (`queryKey: ['scene', id]`). This means both
 * CombatScenePage (using this factory) and SceneDetailPage share the same cache
 * entry and avoid a double fetch. SceneDetailPage uses the legacy shape for now;
 * refactor it to use this factory in a separate PR.
 */
export const sceneKeys = {
  all: ['scene'] as const,
  detail: (id: string | number) => ['scene', String(id)] as const,
};

export type {
  RosterEntryRef,
  SceneParticipant,
  SceneLocation,
  SceneListItem,
  SceneDetail,
  Interaction,
} from './types';

export async function fetchScenes(params: string) {
  const res = await apiFetch(`/api/scenes/?${params}`);
  if (!res.ok) throw new Error('Failed to load scenes');
  return res.json();
}

export async function fetchScene(id: string) {
  const res = await apiFetch(`/api/scenes/${id}/`);
  if (!res.ok) throw new Error('Failed to load scene');
  return res.json();
}

export async function startScene(location: number, name?: string) {
  const res = await apiFetch('/api/scenes/', {
    method: 'POST',
    body: JSON.stringify({ location_id: location, name }),
  });
  if (!res.ok) throw new Error('Failed to start scene');
  return res.json();
}

export async function updateScene(id: string, data: { name?: string; description?: string }) {
  const res = await apiFetch(`/api/scenes/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update scene');
  return res.json();
}

export async function finishScene(id: string) {
  const res = await apiFetch(`/api/scenes/${id}/finish/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to finish scene');
  return res.json();
}

export async function fetchInteractions(sceneId: string, cursor?: string) {
  const url = new URL('/api/interactions/', window.location.origin);
  url.searchParams.set('scene', sceneId);
  if (cursor) url.searchParams.set('cursor', cursor);
  const res = await apiFetch(url.pathname + url.search);
  if (!res.ok) throw new Error('Failed to load interactions');
  return res.json();
}

export async function postInteractionReaction(interactionId: number, emoji: string) {
  const res = await apiFetch('/api/interaction-reactions/', {
    method: 'POST',
    body: JSON.stringify({ interaction: interactionId, emoji }),
  });
  // Toggle returns 201 (created) or 204 (removed) — both are success
  if (!res.ok && res.status !== 204) throw new Error('Failed to toggle reaction');
  return res.status === 204 ? null : res.json();
}

export async function toggleInteractionFavorite(interactionId: number) {
  const res = await apiFetch('/api/interaction-favorites/', {
    method: 'POST',
    body: JSON.stringify({ interaction: interactionId }),
  });
  if (!res.ok && res.status !== 204) throw new Error('Failed to toggle favorite');
  return res.status;
}

export interface PendingUnlinkedActionRow {
  id: number;
  content: string;
  mode: string;
  timestamp: string;
}

export async function fetchPendingUnlinkedActions(
  sceneId: string,
  personaId: number
): Promise<PendingUnlinkedActionRow[]> {
  const url = new URL('/api/interactions/', window.location.origin);
  url.searchParams.set('scene', sceneId);
  url.searchParams.set('persona', String(personaId));
  url.searchParams.set('mode', 'action');
  url.searchParams.set('without_pose_link', 'true');
  const res = await apiFetch(url.pathname + url.search);
  if (!res.ok) throw new Error('Failed to load pending unlinked actions');
  const data = (await res.json()) as { results: PendingUnlinkedActionRow[] };
  return data.results;
}

export interface SubmitPoseBody {
  persona_id: number;
  scene_id?: number;
  content: string;
  /** When provided (including empty array), overrides auto-link. Omit to auto-link. */
  action_link_ids?: number[];
}

export async function submitPose(body: SubmitPoseBody): Promise<void> {
  const res = await apiFetch('/api/interactions/submit-pose/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to submit pose');
}
