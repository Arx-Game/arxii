import { apiFetch } from '@/evennia_replacements/api';

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
