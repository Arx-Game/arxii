/**
 * Organizations React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchOrganizationByName } from './api';

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
