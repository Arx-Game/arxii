import { apiFetch } from '@/evennia_replacements/api';
import type { ConversationSummary, PlayPage, PlaySearchResult, ThreadSummary } from './playTypes';
import type { Interaction } from '@/scenes/types';

export class PlayFetchError extends Error {
  status: number;
  code?: string;
  retry = false;
  constructor(status: number, body?: { code?: string; detail?: string; retry?: string }) {
    super(body?.detail ?? 'Unable to load history');
    this.name = 'PlayFetchError';
    this.status = status;
    this.code = body?.code;
    this.retry = body?.retry === 'reload';
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    let body: { code?: string; detail?: string; retry?: string } | undefined;
    try {
      body = (await response.json()) as typeof body;
    } catch {
      body = undefined;
    }
    throw new PlayFetchError(response.status, body);
  }
  return response.json() as Promise<T>;
}

/** Authorized navigator data. The server owns privacy and language filtering. */
export function fetchPlayConversations(
  params: {
    before?: string;
    after?: string;
    from?: string;
    to?: string;
    all?: boolean;
    kind?: string;
    participant?: string;
    character?: string;
    relevant?: boolean;
  } = {}
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== '') query.set(key, String(value === true ? 1 : value));
  return getJson<PlayPage<ConversationSummary>>(
    `/api/play/conversations/${query.toString() ? `?${query}` : ''}`
  );
}

export function fetchPlaySearch(
  query: string,
  from?: string,
  to?: string,
  kind?: string,
  paging: {
    before?: string;
    after?: string;
    participant?: string;
    character?: string;
    relevant?: boolean;
  } = {}
) {
  const params = new URLSearchParams({ q: query });
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  if (kind) params.set('kind', kind);
  for (const [key, value] of Object.entries(paging))
    if (value !== undefined && value !== '') params.set(key, String(value === true ? 1 : value));
  return getJson<PlayPage<PlaySearchResult>>(`/api/play/search/?${params}`);
}

/** Load an authorized thread page (root pose + visible replies) for a conversation. */
export function fetchPlayThreads(params: {
  conversation: string;
  before?: string;
  after?: string;
}) {
  const query = new URLSearchParams({ conversation: params.conversation });
  if (params.before) query.set('before', params.before);
  if (params.after) query.set('after', params.after);
  return getJson<PlayPage<ThreadSummary>>(`/api/play/threads/?${query}`);
}

/** Load a bounded authorized pose page for a historical reference. */
export function fetchPlayPoses(
  params: { scene?: string; conversation?: string; before?: string; after?: string } = {}
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
  return getJson<PlayPage<Interaction>>(`/api/play/poses/${query.toString() ? `?${query}` : ''}`);
}

/** Mark a batch of poses as read (dwell-tracked by `usePoseReadTracking`). */
export async function markPosesRead(
  poses: { id: number; timestamp: string }[]
): Promise<{ marked: number }> {
  const response = await apiFetch('/api/play/read/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ poses }),
  });
  if (!response.ok) throw new Error('Unable to mark poses read');
  return response.json();
}

/**
 * Mark-all-before-snapshot bulk dismissal (#3759 spec section 7): mark every
 * interaction the account can see in `conversation` with timestamp <= `before`
 * as read, in one call, instead of enumerating individual poses like
 * `markPosesRead`. Same endpoint, alternate request body shape (see
 * `PlayReadView` on the backend).
 */
export async function markConversationRead(
  conversation: string,
  before: string
): Promise<{ marked: number }> {
  const response = await apiFetch('/api/play/read/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation, before }),
  });
  if (!response.ok) throw new Error('Unable to mark conversation read');
  return response.json();
}

/** Load the authorized neighborhood around one historical pose. */
export function fetchPlayContext(params: {
  id: string;
  scene?: string;
  timestamp?: string;
  conversation?: string;
  from?: string;
  before?: string;
  after?: string;
}) {
  const query = new URLSearchParams({ id: params.id });
  if (params.scene) query.set('scene', params.scene);
  if (params.timestamp) query.set('timestamp', params.timestamp);
  if (params.conversation) query.set('conversation', params.conversation);
  if (params.from) query.set('from', params.from);
  if (params.before) query.set('before', params.before);
  if (params.after) query.set('after', params.after);
  return getJson<{
    results: Interaction[];
    threadId: string | null;
    before: string | null;
    after: string | null;
  }>(`/api/play/context/?${query}`);
}

/** Load one bounded page of poses inside an authorized reply thread/reference. */
export function fetchPlayThreadPoses(params: {
  thread: string;
  conversation?: string;
  before?: string;
  after?: string;
  from?: string;
  to?: string;
}) {
  const query = new URLSearchParams({ thread: params.thread });
  for (const key of ['conversation', 'before', 'after', 'from', 'to'] as const) {
    const value = params[key];
    if (value) query.set(key, value);
  }
  return getJson<PlayPage<Interaction>>(`/api/play/poses/?${query}`);
}
