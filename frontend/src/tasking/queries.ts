/**
 * Tasking React Query hooks (#2820 phase 1).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchListenerPosts, fetchOrgRoster, fetchOrgTasks } from './api';

/**
 * The org's task board rows. Server-side scoping means a non-member simply
 * gets an empty board — callers hide the panel on empty rather than erroring.
 */
export function useOrgTasksQuery(orgId: number) {
  return useQuery({
    queryKey: ['tasking', 'board', orgId],
    queryFn: () => fetchOrgTasks(orgId),
    enabled: orgId > 0,
  });
}

/** The org's held agents (Roster panel). Empty for non-members. */
export function useOrgRosterQuery(orgId: number) {
  return useQuery({
    queryKey: ['tasking', 'roster', orgId],
    queryFn: () => fetchOrgRoster(orgId),
    enabled: orgId > 0,
  });
}

/** Visible listener posts (Postings panel), scoped server-side. */
export function useListenerPostsQuery() {
  return useQuery({
    queryKey: ['tasking', 'posts'],
    queryFn: () => fetchListenerPosts(),
  });
}
