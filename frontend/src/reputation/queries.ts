/**
 * React Query hooks for the consolidated Reputation tab (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import {
  fetchOrganizationReputations,
  fetchOrganizationMemberships,
  fetchCovenantRolesForSheet,
} from './api';

/** The viewer's own org standing (Standing card). Own-view only — pass `enabled=false` otherwise. */
export function useOrganizationReputationsQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['reputation', 'organization-reputations'],
    queryFn: fetchOrganizationReputations,
    enabled,
  });
}

/** The viewer's own org memberships (Standing card). Own-view only. */
export function useOrganizationMembershipsQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['reputation', 'organization-memberships'],
    queryFn: fetchOrganizationMemberships,
    enabled,
  });
}

/** Active covenant role assignments for a character sheet (Covenants card). Own-view only. */
export function useCovenantRolesQuery(characterSheetId: number | null) {
  return useQuery({
    queryKey: ['reputation', 'covenant-roles', characterSheetId],
    queryFn: () => fetchCovenantRolesForSheet(characterSheetId as number),
    enabled: characterSheetId !== null,
  });
}
