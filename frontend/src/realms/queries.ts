/**
 * Realm page React Query hooks (#3725).
 *
 * None set `throwOnError`: a realm page degrades section by section (an empty
 * board, no houses yet) rather than tripping an error boundary, the same posture
 * as the landing page's hooks. Every hook is rendered against possibly-`undefined`
 * data.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchRosterEntries } from '@/roster/api';
import type { RosterEntryData } from '@/roster/types';
import type { PaginatedResponse } from '@/shared/types';
import { getRealm, getRealmNotables, getRealmOrganizations, getRealms } from './api';
import type { RealmBoards, RealmDetail, RealmListItem, RealmOrganization } from './types';

const FIVE_MINUTES = 5 * 60 * 1000;

export const realmKeys = {
  all: ['realms'] as const,
  list: () => [...realmKeys.all, 'list'] as const,
  detail: (slug: string) => [...realmKeys.all, 'detail', slug] as const,
  organizations: (slug: string) => [...realmKeys.all, 'organizations', slug] as const,
  notables: (slug: string) => [...realmKeys.all, 'notables', slug] as const,
  roster: (slug: string) => [...realmKeys.all, 'roster', slug] as const,
};

export function useRealms() {
  return useQuery<RealmListItem[]>({
    queryKey: realmKeys.list(),
    queryFn: getRealms,
    staleTime: FIVE_MINUTES,
  });
}

export function useRealm(slug: string | undefined) {
  return useQuery<RealmDetail>({
    queryKey: realmKeys.detail(slug ?? ''),
    queryFn: () => getRealm(slug as string),
    enabled: !!slug,
    staleTime: FIVE_MINUTES,
  });
}

export function useRealmOrganizations(slug: string | undefined) {
  return useQuery<RealmOrganization[]>({
    queryKey: realmKeys.organizations(slug ?? ''),
    queryFn: () => getRealmOrganizations(slug as string),
    enabled: !!slug,
    staleTime: FIVE_MINUTES,
  });
}

export function useRealmNotables(slug: string | undefined) {
  return useQuery<RealmBoards>({
    queryKey: realmKeys.notables(slug ?? ''),
    queryFn: () => getRealmNotables(slug as string),
    enabled: !!slug,
    staleTime: FIVE_MINUTES,
  });
}

/** The realm's characters across every public roster, first page (the roster read's `realm` filter). */
export function useRealmRoster(slug: string | undefined) {
  return useQuery<PaginatedResponse<RosterEntryData>>({
    queryKey: realmKeys.roster(slug ?? ''),
    queryFn: () => fetchRosterEntries(undefined, 1, { realm: slug as string }),
    enabled: !!slug,
    staleTime: FIVE_MINUTES,
  });
}
