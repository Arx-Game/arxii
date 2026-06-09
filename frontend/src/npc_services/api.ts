/**
 * NPC-services staff editor API wrappers (#728 — Mission Studio).
 *
 * Pure functions over the shipped `/api/npc-services/*` endpoints (all
 * staff-only, IsAdminUser on the backend). Pair with the React Query hooks in
 * queries.ts. Reuses the Mission Studio error helpers so DRF error shapes
 * surface identically across the two editors.
 */
import { ApiValidationError } from '@/missions/api';

import { apiFetch } from '@/evennia_replacements/api';

import type {
  MissionOfferDetails,
  MissionOfferDetailsRequest,
  NPCRole,
  NPCRoleFilters,
  NPCRoleRequest,
  NPCServiceOffer,
  NPCServiceOfferRequest,
  PaginatedResponse,
} from './types';

export { ApiValidationError, flattenErrorMessage } from '@/missions/api';

const BASE_URL = '/api/npc-services';

function buildQueryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.append(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}

async function writeJson<T>(url: string, method: string, body: unknown): Promise<T> {
  const res = await apiFetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiValidationError(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// NPCRole
// ---------------------------------------------------------------------------

export async function listRoles(filters: NPCRoleFilters = {}): Promise<PaginatedResponse<NPCRole>> {
  const res = await apiFetch(`${BASE_URL}/roles/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load NPC roles');
  return res.json();
}

export async function getRole(id: number): Promise<NPCRole> {
  const res = await apiFetch(`${BASE_URL}/roles/${id}/`);
  if (!res.ok) throw new Error(`Failed to load role ${id}`);
  return res.json();
}

export function createRole(body: NPCRoleRequest): Promise<NPCRole> {
  return writeJson(`${BASE_URL}/roles/`, 'POST', body);
}

export function patchRole(id: number, body: Partial<NPCRoleRequest>): Promise<NPCRole> {
  return writeJson(`${BASE_URL}/roles/${id}/`, 'PATCH', body);
}

export async function deleteRole(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/roles/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete role ${id}`);
}

// ---------------------------------------------------------------------------
// NPCServiceOffer
// ---------------------------------------------------------------------------

export async function listOffers(
  filters: { role?: number; kind?: string; page_size?: number } = {}
): Promise<PaginatedResponse<NPCServiceOffer>> {
  const res = await apiFetch(`${BASE_URL}/offers/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load offers');
  return res.json();
}

export function createOffer(body: NPCServiceOfferRequest): Promise<NPCServiceOffer> {
  return writeJson(`${BASE_URL}/offers/`, 'POST', body);
}

export function patchOffer(
  id: number,
  body: Partial<NPCServiceOfferRequest>
): Promise<NPCServiceOffer> {
  return writeJson(`${BASE_URL}/offers/${id}/`, 'PATCH', body);
}

export async function deleteOffer(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/offers/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete offer ${id}`);
}

// ---------------------------------------------------------------------------
// MissionOfferDetails (per mission-kind offer)
// ---------------------------------------------------------------------------

export async function listMissionDetails(
  filters: { offer?: number; role?: number; page_size?: number } = {}
): Promise<PaginatedResponse<MissionOfferDetails>> {
  const res = await apiFetch(`${BASE_URL}/mission-details/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load mission offer details');
  return res.json();
}

export function createMissionDetails(
  body: MissionOfferDetailsRequest
): Promise<MissionOfferDetails> {
  return writeJson(`${BASE_URL}/mission-details/`, 'POST', body);
}

export function patchMissionDetails(
  id: number,
  body: Partial<MissionOfferDetailsRequest>
): Promise<MissionOfferDetails> {
  return writeJson(`${BASE_URL}/mission-details/${id}/`, 'PATCH', body);
}
