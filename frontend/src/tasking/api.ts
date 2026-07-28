/**
 * Tasking API client (#2820 phase 1) — the org task board.
 *
 * Reads `/api/tasking/tasks/` scoped server-side to orgs the requester's
 * active persona belongs to. A non-member sees an empty list, not an error.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type OrgTask = components['schemas']['OrgTask'];
export type PaginatedOrgTasks = components['schemas']['PaginatedOrgTaskList'];
export type OrgAgent = components['schemas']['NPCAsset'];
export type ListenerPost = components['schemas']['ListenerPost'];

interface Paginated<T> {
  results: T[];
}

/**
 * Fetch the org's task board rows.
 * GET /api/tasking/tasks/?org={orgId}
 */
export async function fetchOrgTasks(orgId: number): Promise<OrgTask[]> {
  const res = await apiFetch(`/api/tasking/tasks/?org=${orgId}`);
  if (!res.ok) throw new Error('Failed to load the task board');
  const data = (await res.json()) as PaginatedOrgTasks;
  return data.results;
}

/**
 * Fetch the org's held agents (the Roster panel).
 * GET /api/tasking/roster/?org={orgId}
 */
export async function fetchOrgRoster(orgId: number): Promise<OrgAgent[]> {
  const res = await apiFetch(`/api/tasking/roster/?org=${orgId}`);
  if (!res.ok) throw new Error('Failed to load the roster');
  const data = (await res.json()) as Paginated<OrgAgent>;
  return data.results;
}

/**
 * Fetch visible listener posts (the Postings panel). Server-side scoped to
 * the viewer's networks; buzz shows as-is — a frozen meter and an unlucky
 * one are indistinguishable by design.
 * GET /api/tasking/posts/
 */
export async function fetchListenerPosts(): Promise<ListenerPost[]> {
  const res = await apiFetch(`/api/tasking/posts/`);
  if (!res.ok) throw new Error('Failed to load postings');
  const data = (await res.json()) as Paginated<ListenerPost>;
  return data.results;
}
