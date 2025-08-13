import { apiFetch } from '../evennia_replacements/api';

export interface RosterEntryRef {
  id: number;
  name: string;
}

export interface SceneParticipant {
  id: number;
  name: string;
  roster_entry?: RosterEntryRef | null;
}

export interface SceneLocation {
  id: number;
  name: string;
}

export interface SceneListItem {
  id: number;
  name: string;
  description: string;
  date_started: string;
  location?: SceneLocation | null;
  participants: SceneParticipant[];
}

export interface SceneDetail extends SceneListItem {
  highlight_message: SceneMessage | null;
  is_active: boolean;
  is_owner: boolean;
}

export interface SceneMessage {
  id: number;
  persona: { id: number; name: string; thumbnail_url?: string };
  content: string;
  timestamp: string;
  reactions: { emoji: string; count: number; reacted: boolean }[];
}

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

export async function fetchSceneMessages(scene: string, cursor?: string) {
  const url = new URL('/api/messages/', window.location.origin);
  url.searchParams.set('scene', scene);
  if (cursor) url.searchParams.set('cursor', cursor);
  const res = await apiFetch(url.pathname + url.search);
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postReaction(message: number, emoji: string) {
  const res = await apiFetch('/api/reactions/', {
    method: 'POST',
    body: JSON.stringify({ message, emoji }),
  });
  if (!res.ok) throw new Error('Failed to add reaction');
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
