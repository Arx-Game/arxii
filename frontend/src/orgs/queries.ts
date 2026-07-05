/**
 * Organizations React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchOrganizationByName, fetchOrganizationById } from './api';

/**
 * Resolve a same-named organization for a character's family (link target).
 * Disabled when `name` is empty — the character sheet renders plain text in that case.
 */
export function useOrganizationByName(name: string) {
  return useQuery({
    queryKey: ['orgs', 'byName', name],
    queryFn: () => fetchOrganizationByName(name),
    enabled: name.length > 0,
  });
}

/**
 * Fetch a single organization by id, for the org detail stub page (#1446).
 * A members-only 404 surfaces as `isError` — the page renders the not-yet-public
 * placeholder rather than treating it as a hard failure.
 */
export function useOrganizationQuery(orgId: number) {
  return useQuery({
    queryKey: ['orgs', 'detail', orgId],
    queryFn: () => fetchOrganizationById(orgId),
    enabled: orgId > 0,
  });
}
