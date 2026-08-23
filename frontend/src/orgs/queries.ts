/**
 * Organizations React Query hooks (#1446).
 */

import { chooseCrisisOption } from '@/orgs/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchHouseFeed,
  fetchOrganizationById,
  fetchOrganizationByName,
  fetchOrgAppeals,
  fetchStandingDeclarations,
  lodgeOrgAppeal,
  resolveOrgAppeal,
  signonOrgAppeal,
  withdrawOrgAppeal,
} from './api';

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

/** This org's public standing-declaration history (#3290), newest first. */
export function useStandingDeclarationsQuery(orgId: number) {
  return useQuery({
    queryKey: ['orgs', 'standingDeclarations', orgId],
    queryFn: () => fetchStandingDeclarations(orgId),
    enabled: orgId > 0,
  });
}

// ---------------------------------------------------------------------------
// Appeals to organizations (#3293)
// ---------------------------------------------------------------------------

const appealsQueryKey = (orgId: number) => ['orgs', 'appeals', orgId];

/** List appeals for one organization, member-gated on the backend. */
export function useOrgAppealsQuery(orgId: number) {
  return useQuery({
    queryKey: appealsQueryKey(orgId),
    queryFn: () => fetchOrgAppeals(orgId),
    enabled: orgId > 0,
  });
}

/** Lodge an appeal — the outsider dialog on the org's public dossier page. */
export function useLodgeOrgAppealMutation(orgId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ title, body }: { title: string; body: string }) =>
      lodgeOrgAppeal(orgId, title, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: appealsQueryKey(orgId) }).catch(() => {});
    },
  });
}

/** Sign onto an open appeal. */
export function useSignonOrgAppealMutation(orgId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appealId, note }: { appealId: number; note: string }) =>
      signonOrgAppeal(appealId, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: appealsQueryKey(orgId) }).catch(() => {});
    },
  });
}

/** Grant/decline an open appeal — leadership only (backend-enforced). */
export function useResolveOrgAppealMutation(orgId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      appealId,
      verdict,
      answer,
    }: {
      appealId: number;
      verdict: 'grant' | 'decline';
      answer: string;
    }) => resolveOrgAppeal(appealId, verdict, answer),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: appealsQueryKey(orgId) }).catch(() => {});
    },
  });
}

/** Withdraw your own open appeal. */
export function useWithdrawOrgAppealMutation(orgId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (appealId: number) => withdrawOrgAppeal(appealId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: appealsQueryKey(orgId) }).catch(() => {});
    },
  });
}
