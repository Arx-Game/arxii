/**
 * Tasking React Query hooks (#2820 phase 1).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchOrgTasks } from './api';

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
