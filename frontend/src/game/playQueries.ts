import { apiFetch } from '@/evennia_replacements/api';
import type { ConversationSummary, PlayPage, PlaySearchResult } from './playTypes';
import type { Interaction } from '@/scenes/types';

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error('Unable to load history');
  return response.json() as Promise<T>;
}

/** Authorized navigator data. The server owns privacy and language filtering. */
export function fetchPlayConversations(
  params: { before?: string; after?: string; from?: string; to?: string } = {}
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
  return getJson<PlayPage<ConversationSummary>>(
    `/api/play/conversations/${query.toString() ? `?${query}` : ''}`
  );
}

export function fetchPlaySearch(query: string, from?: string, to?: string) {
  const params = new URLSearchParams({ q: query });
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  return getJson<PlayPage<PlaySearchResult>>(`/api/play/search/?${params}`);
}

/** Load a bounded authorized pose page for a historical reference. */
export function fetchPlayPoses(
  params: { scene?: string; conversation?: string; before?: string; after?: string } = {}
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
  return getJson<PlayPage<Interaction>>(`/api/play/poses/${query.toString() ? `?${query}` : ''}`);
}

/** Load the authorized neighborhood around one historical pose. */
export function fetchPlayContext(params: {
  id: string;
  scene?: string;
  timestamp?: string;
  conversation?: string;
}) {
  const query = new URLSearchParams({ id: params.id });
  if (params.scene) query.set('scene', params.scene);
  if (params.timestamp) query.set('timestamp', params.timestamp);
  if (params.conversation) query.set('conversation', params.conversation);
  return getJson<{ results: Interaction[]; threadId: string | null }>(
    `/api/play/context/?${query}`
  );
}
