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
