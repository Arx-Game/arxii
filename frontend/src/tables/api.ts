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
  BulletinPostCreateBody,
  BulletinPostUpdateBody,
  BulletinReplyCreateBody,
  BulletinReplyUpdateBody,
  GMTable,
  GMTableCreateBody,
  GMTableMembership,
  GMTableMembershipCreateBody,
  GMTableTransferBody,
  GMTableUpdateBody,
  PaginatedBulletinPosts,
  PaginatedBulletinReplies,
  PaginatedMemberships,
  PaginatedTables,
  TableBulletinPost,
  TableBulletinReply,
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
const BULLETIN_POSTS_URL = '/api/table-bulletin-posts';
const BULLETIN_REPLIES_URL = '/api/table-bulletin-replies';

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

// ---------------------------------------------------------------------------
// Bulletin Posts
// ---------------------------------------------------------------------------

export interface ListBulletinPostsParams {
  table?: number;
  story?: number | null;
  page?: number;
  page_size?: number;
}

/**
 * GET /api/table-bulletin-posts/?table=<id>&story=<id>
 * The queryset is already permission-filtered by the backend.
 */
export async function getBulletinPosts(
  params?: ListBulletinPostsParams
): Promise<PaginatedBulletinPosts> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`${BULLETIN_POSTS_URL}/${qs}`);
  if (!res.ok) throw new Error('Failed to load bulletin posts');
  return res.json() as Promise<PaginatedBulletinPosts>;
}

/**
 * POST /api/table-bulletin-posts/
 * GM/staff only. Creates a new bulletin post (table-wide or story-scoped).
 */
export async function createBulletinPost(data: BulletinPostCreateBody): Promise<TableBulletinPost> {
  const res = await apiFetch(`${BULLETIN_POSTS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create bulletin post');
  return res.json() as Promise<TableBulletinPost>;
}

/**
 * PATCH /api/table-bulletin-posts/{id}/
 * Author edits (title, body, allow_replies).
 */
export async function updateBulletinPost(
  id: number,
  data: BulletinPostUpdateBody
): Promise<TableBulletinPost> {
  const res = await apiFetch(`${BULLETIN_POSTS_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update bulletin post ${id}`);
  return res.json() as Promise<TableBulletinPost>;
}

/**
 * DELETE /api/table-bulletin-posts/{id}/
 * Author deletes.
 */
export async function deleteBulletinPost(id: number): Promise<void> {
  const res = await apiFetch(`${BULLETIN_POSTS_URL}/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete bulletin post ${id}`);
}

// ---------------------------------------------------------------------------
// Bulletin Replies
// ---------------------------------------------------------------------------

export interface ListBulletinRepliesParams {
  post?: number;
  page?: number;
  page_size?: number;
}

/**
 * GET /api/table-bulletin-replies/?post=<id>
 */
export async function getBulletinReplies(
  params?: ListBulletinRepliesParams
): Promise<PaginatedBulletinReplies> {
  const qs = buildQueryString(
    (params as Record<string, string | number | boolean | undefined>) ?? {}
  );
  const res = await apiFetch(`${BULLETIN_REPLIES_URL}/${qs}`);
  if (!res.ok) throw new Error('Failed to load bulletin replies');
  return res.json() as Promise<PaginatedBulletinReplies>;
}

/**
 * POST /api/table-bulletin-replies/
 * Qualifying readers can reply if allow_replies is true.
 */
export async function createBulletinReply(
  data: BulletinReplyCreateBody
): Promise<TableBulletinReply> {
  const res = await apiFetch(`${BULLETIN_REPLIES_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create bulletin reply');
  return res.json() as Promise<TableBulletinReply>;
}

/**
 * PATCH /api/table-bulletin-replies/{id}/
 * Author edits.
 */
export async function updateBulletinReply(
  id: number,
  data: BulletinReplyUpdateBody
): Promise<TableBulletinReply> {
  const res = await apiFetch(`${BULLETIN_REPLIES_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update bulletin reply ${id}`);
  return res.json() as Promise<TableBulletinReply>;
}

/**
 * DELETE /api/table-bulletin-replies/{id}/
 * Author deletes.
 */
export async function deleteBulletinReply(id: number): Promise<void> {
  const res = await apiFetch(`${BULLETIN_REPLIES_URL}/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete bulletin reply ${id}`);
}
