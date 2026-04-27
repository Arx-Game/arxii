/**
 * Tables API functions
 *
 * Covers GMTableViewSet (/api/gm/tables/) and GMTableMembershipViewSet
 * (/api/gm/table-memberships/) from the Phase 5 Stories backend.
 *
 * Action endpoints:
 *   POST /api/gm/tables/{id}/archive/
 *   POST /api/gm/tables/{id}/transfer_ownership/
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  GMTable,
  GMTableCreateBody,
  GMTableMembership,
  GMTableMembershipCreateBody,
  GMTableTransferBody,
  GMTableUpdateBody,
  PaginatedMemberships,
  PaginatedTables,
} from './types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
// URL constants
// ---------------------------------------------------------------------------

const TABLES_URL = '/api/gm/tables';
const MEMBERSHIPS_URL = '/api/gm/table-memberships';

// ---------------------------------------------------------------------------
// Tables CRUD
// ---------------------------------------------------------------------------

export interface ListTablesParams {
  status?: string;
  gm?: number;
  page?: number;
  page_size?: number;
}

export async function getTables(params?: ListTablesParams): Promise<PaginatedTables> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`${TABLES_URL}/${qs}`);
  if (!res.ok) throw new Error('Failed to load tables');
  return res.json() as Promise<PaginatedTables>;
}

export async function getTable(id: number): Promise<GMTable> {
  const res = await apiFetch(`${TABLES_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load table ${id}`);
  return res.json() as Promise<GMTable>;
}

export async function createTable(data: GMTableCreateBody): Promise<GMTable> {
  const res = await apiFetch(`${TABLES_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create table');
  return res.json() as Promise<GMTable>;
}

export async function updateTable(id: number, data: GMTableUpdateBody): Promise<GMTable> {
  const res = await apiFetch(`${TABLES_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update table ${id}`);
  return res.json() as Promise<GMTable>;
}

// ---------------------------------------------------------------------------
// Action endpoints
// ---------------------------------------------------------------------------

/**
 * POST /api/gm/tables/{id}/archive/
 * Archives the table (sets status to ARCHIVED).
 */
export async function archiveTable(id: number): Promise<GMTable> {
  const res = await apiFetch(`${TABLES_URL}/${id}/archive/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Failed to archive table ${id}`);
  return res.json() as Promise<GMTable>;
}

/**
 * POST /api/gm/tables/{id}/transfer_ownership/
 * Transfers GM ownership to another GMProfile.
 */
export async function transferOwnership(id: number, data: GMTableTransferBody): Promise<GMTable> {
  const res = await apiFetch(`${TABLES_URL}/${id}/transfer_ownership/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to transfer ownership of table ${id}`);
  return res.json() as Promise<GMTable>;
}

// ---------------------------------------------------------------------------
// Memberships CRUD
// ---------------------------------------------------------------------------

export interface ListMembershipsParams {
  table?: number;
  persona?: number;
  active?: boolean;
  page?: number;
  page_size?: number;
}

export async function getTableMemberships(
  params?: ListMembershipsParams
): Promise<PaginatedMemberships> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`${MEMBERSHIPS_URL}/${qs}`);
  if (!res.ok) throw new Error('Failed to load memberships');
  return res.json() as Promise<PaginatedMemberships>;
}

/**
 * POST /api/gm/table-memberships/
 * GM invites a persona to the table.
 */
export async function inviteToTable(data: GMTableMembershipCreateBody): Promise<GMTableMembership> {
  const res = await apiFetch(`${MEMBERSHIPS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to invite persona to table');
  return res.json() as Promise<GMTableMembership>;
}

/**
 * DELETE /api/gm/table-memberships/{id}/
 * Soft-leave: sets left_at on the membership record.
 * Used by both "leave" (player self-removes) and "remove" (GM removes member).
 */
export async function removeMembership(id: number): Promise<void> {
  const res = await apiFetch(`${MEMBERSHIPS_URL}/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to remove membership ${id}`);
}

/**
 * DELETE /api/gm/table-memberships/{id}/
 * Alias for removeMembership — used in "leave table" flow where the
 * member themselves initiate removal.
 */
export async function leaveTable(membershipId: number): Promise<void> {
  return removeMembership(membershipId);
}
