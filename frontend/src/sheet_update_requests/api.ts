/**
 * Sheet update requests API (#2631).
 *
 * TableUpdateRequestViewSet:
 *   GET/POST /api/gm/table-update-requests/
 *   POST /api/gm/table-update-requests/{id}/signoff/
 *   POST /api/gm/table-update-requests/{id}/withdraw/
 * Timeline:
 *   GET /api/character-sheets/{id}/profile-text-versions/
 * Accepting an approved distinction change dispatches the registry action
 * `accept_distinction_change` through the unified dispatch endpoint.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

import type {
  CreateUpdateRequestBody,
  PaginatedTableUpdateRequests,
  ProfileTextVersion,
  SignoffBody,
  TableUpdateRequest,
} from './types';

const REQUESTS_URL = '/api/gm/table-update-requests';

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

export interface ListRequestsParams {
  role?: 'mine' | 'gm';
  status?: string;
  kind?: string;
}

export async function listUpdateRequests(
  params?: ListRequestsParams
): Promise<PaginatedTableUpdateRequests> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) search.set(key, String(value));
  }
  const qs = search.toString();
  const res = await apiFetch(`${REQUESTS_URL}/${qs ? `?${qs}` : ''}`);
  if (!res.ok) await throwApiError(res, 'Failed to load update requests');
  return res.json() as Promise<PaginatedTableUpdateRequests>;
}

export async function createUpdateRequest(
  body: CreateUpdateRequestBody
): Promise<TableUpdateRequest> {
  const res = await apiFetch(`${REQUESTS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res, 'Failed to submit update request');
  return res.json() as Promise<TableUpdateRequest>;
}

export async function signoffUpdateRequest(
  id: number,
  body: SignoffBody
): Promise<TableUpdateRequest> {
  const res = await apiFetch(`${REQUESTS_URL}/${id}/signoff/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res, 'Failed to sign off on request');
  return res.json() as Promise<TableUpdateRequest>;
}

export async function withdrawUpdateRequest(id: number): Promise<TableUpdateRequest> {
  const res = await apiFetch(`${REQUESTS_URL}/${id}/withdraw/`, { method: 'POST' });
  if (!res.ok) await throwApiError(res, 'Failed to withdraw request');
  return res.json() as Promise<TableUpdateRequest>;
}

export async function fetchProfileTextVersions(sheetId: number): Promise<ProfileTextVersion[]> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/profile-text-versions/`);
  if (!res.ok) await throwApiError(res, 'Failed to load profile history');
  return res.json() as Promise<ProfileTextVersion[]>;
}

/** Accept an approved distinction change: spend the XP via the dispatch seam. */
export async function acceptDistinctionChange(
  characterId: number,
  authorizationId: number
): Promise<{ success?: boolean | null; message?: string | null }> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({
      ref: { backend: 'registry', registry_key: 'accept_distinction_change' },
      kwargs: { authorization_id: authorizationId },
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to accept the change');
  return res.json() as Promise<{ success?: boolean | null; message?: string | null }>;
}
