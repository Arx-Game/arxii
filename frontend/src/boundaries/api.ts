import { apiFetch } from '@/evennia_replacements/api';
import type {
  PaginatedContentThemeList,
  PaginatedPlayerBoundaryList,
  PaginatedTreasuredSignoffList,
  PaginatedTreasuredSubjectList,
  PatchedPlayerBoundaryRequest,
  PatchedTreasuredSubjectRequest,
  PlayerBoundary,
  PlayerBoundaryRequest,
  SceneLinesAndVeils,
  TreasuredSignoff,
  TreasuredSignoffRequest,
  TreasuredSubject,
  TreasuredSubjectRequest,
} from './types';

// ---------------------------------------------------------------------------
// Content themes (read-only, shared catalog)
// ---------------------------------------------------------------------------

export async function fetchContentThemes(): Promise<PaginatedContentThemeList> {
  const res = await apiFetch('/api/boundaries/content-themes/?is_active=true');
  if (!res.ok) {
    throw new Error('Failed to load content themes');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// PlayerBoundary (owner-scoped, account-wide — hard lines + advisories)
// ---------------------------------------------------------------------------

export async function fetchPlayerBoundaries(): Promise<PaginatedPlayerBoundaryList> {
  const res = await apiFetch('/api/boundaries/player-boundaries/');
  if (!res.ok) {
    throw new Error('Failed to load boundaries');
  }
  return res.json();
}

export async function createPlayerBoundary(body: PlayerBoundaryRequest): Promise<PlayerBoundary> {
  const res = await apiFetch('/api/boundaries/player-boundaries/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to create boundary');
  }
  return res.json();
}

export async function updatePlayerBoundary(
  id: number,
  body: PatchedPlayerBoundaryRequest
): Promise<PlayerBoundary> {
  const res = await apiFetch(`/api/boundaries/player-boundaries/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to update boundary');
  }
  return res.json();
}

export async function deletePlayerBoundary(id: number): Promise<void> {
  const res = await apiFetch(`/api/boundaries/player-boundaries/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to delete boundary');
  }
}

// ---------------------------------------------------------------------------
// TreasuredSubject (owner-scoped, per-tenure attachments)
// ---------------------------------------------------------------------------

export async function fetchTreasuredSubjects(
  tenureId: number
): Promise<PaginatedTreasuredSubjectList> {
  const res = await apiFetch(`/api/boundaries/treasured-subjects/?owner=${tenureId}`);
  if (!res.ok) {
    throw new Error('Failed to load treasured subjects');
  }
  return res.json();
}

export async function createTreasuredSubject(
  body: TreasuredSubjectRequest
): Promise<TreasuredSubject> {
  const res = await apiFetch('/api/boundaries/treasured-subjects/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to create treasured subject');
  }
  return res.json();
}

export async function updateTreasuredSubject(
  id: number,
  body: PatchedTreasuredSubjectRequest
): Promise<TreasuredSubject> {
  const res = await apiFetch(`/api/boundaries/treasured-subjects/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to update treasured subject');
  }
  return res.json();
}

export async function deleteTreasuredSubject(id: number): Promise<void> {
  const res = await apiFetch(`/api/boundaries/treasured-subjects/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to delete treasured subject');
  }
}

// ---------------------------------------------------------------------------
// TreasuredSignoff (grant / withdraw pre-scene sign-off)
// ---------------------------------------------------------------------------

export async function fetchTreasuredSignoffs(params: {
  beat?: number;
  treasured_subject?: number;
}): Promise<PaginatedTreasuredSignoffList> {
  const query = new URLSearchParams();
  if (params.beat != null) query.set('beat', String(params.beat));
  if (params.treasured_subject != null) {
    query.set('treasured_subject', String(params.treasured_subject));
  }
  const res = await apiFetch(`/api/treasured-signoffs/?${query.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load sign-offs');
  }
  return res.json();
}

export async function grantTreasuredSignoff(
  body: TreasuredSignoffRequest
): Promise<TreasuredSignoff> {
  const res = await apiFetch('/api/treasured-signoffs/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to grant sign-off');
  }
  return res.json();
}

export async function withdrawTreasuredSignoff(id: number): Promise<TreasuredSignoff> {
  const res = await apiFetch(`/api/treasured-signoffs/${id}/withdraw/`, { method: 'POST' });
  if (!res.ok) {
    throw new Error('Failed to withdraw sign-off');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Scene "lines & veils" aggregate (read-only)
// ---------------------------------------------------------------------------

export async function fetchSceneLinesAndVeils(
  sceneId: string | number,
  tenureId: number
): Promise<SceneLinesAndVeils> {
  const res = await apiFetch(
    `/api/boundaries/scenes/${sceneId}/lines-and-veils/?tenure=${tenureId}`
  );
  if (!res.ok) {
    throw new Error('Failed to load scene lines & veils');
  }
  return res.json();
}
