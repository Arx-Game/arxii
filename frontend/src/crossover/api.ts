/** API client for crossover invites (#2075). */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type {
  CrossoverInvite,
  CrossoverInviteAcceptBody,
  CrossoverInviteCreateBody,
  EpisodeScene,
  ListCrossoverInvitesParams,
  PaginatedResponse,
} from './types';

export type StakesSummary = components['schemas']['StakesSummary'];

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

// ---------------------------------------------------------------------------
// CrossoverInvite CRUD + actions
// ---------------------------------------------------------------------------

export async function listCrossoverInvites(
  params?: ListCrossoverInvitesParams
): Promise<PaginatedResponse<CrossoverInvite>> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`/api/crossover-invites/${qs}`);
  if (!res.ok) throw new Error('Failed to load crossover invites');
  return res.json() as Promise<PaginatedResponse<CrossoverInvite>>;
}

export async function createCrossoverInvite(
  body: CrossoverInviteCreateBody
): Promise<CrossoverInvite> {
  const res = await apiFetch('/api/crossover-invites/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json();
    throw err;
  }
  return res.json() as Promise<CrossoverInvite>;
}

export async function acceptCrossoverInvite(
  id: number,
  body: CrossoverInviteAcceptBody
): Promise<CrossoverInvite> {
  const res = await apiFetch(`/api/crossover-invites/${id}/accept/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json();
    throw err;
  }
  return res.json() as Promise<CrossoverInvite>;
}

export async function declineCrossoverInvite(
  id: number,
  responseNote?: string
): Promise<CrossoverInvite> {
  const res = await apiFetch(`/api/crossover-invites/${id}/decline/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ response_note: responseNote ?? '' }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw err;
  }
  return res.json() as Promise<CrossoverInvite>;
}

export async function withdrawCrossoverInvite(id: number): Promise<CrossoverInvite> {
  const res = await apiFetch(`/api/crossover-invites/${id}/withdraw/`, {
    method: 'POST',
    headers: jsonHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    throw err;
  }
  return res.json() as Promise<CrossoverInvite>;
}

// ---------------------------------------------------------------------------
// EpisodeScene (for linked-stories panel)
// ---------------------------------------------------------------------------

export async function listEpisodeScenesForScene(
  sceneId: number
): Promise<PaginatedResponse<EpisodeScene>> {
  const res = await apiFetch(`/api/episode-scenes/?scene=${sceneId}`);
  if (!res.ok) throw new Error('Failed to load episode scenes');
  return res.json() as Promise<PaginatedResponse<EpisodeScene>>;
}

// ---------------------------------------------------------------------------
// Stakes summary (for linked-stories panel)
// ---------------------------------------------------------------------------

export async function getStakesSummary(beatId: number): Promise<StakesSummary> {
  const res = await apiFetch(`/api/beats/${beatId}/stakes-summary/`);
  if (!res.ok) throw new Error(`Failed to load stakes summary for beat ${beatId}`);
  return res.json() as Promise<StakesSummary>;
}
