/**
 * Organizations React Query hooks (#1446).
 */

import { chooseCrisisOption } from '@/orgs/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchOrganizationByName, fetchOrganizationById, fetchHouseFeed } from './api';

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

/**
 * Fetch the house feed for a house org (#1884). Only enabled when the org
 * has a house block — non-family orgs never fire it.
 */
export function useHouseFeedQuery(orgId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['orgs', 'houseFeed', orgId],
    queryFn: () => fetchHouseFeed(orgId),
    enabled: enabled && orgId > 0,
  });
}

/** Judgment call on an open domain crisis (#2238); refreshes the org detail. */
export function useChooseCrisisOption(orgId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ crisisId, optionId }: { crisisId: number; optionId: number }) =>
      chooseCrisisOption(orgId, crisisId, optionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['orgs', 'detail', orgId] }).catch(() => {});
      qc.invalidateQueries({ queryKey: ['orgs', 'houseFeed', orgId] }).catch(() => {});
    },
  });
}
