import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchRosterEntry,
  fetchMyRosterEntries,
  fetchRosters,
  fetchRosterEntries,
  postRosterApplication,
} from './api';
import type { RosterEntryData } from './types';
import type { PaginatedResponse } from '@/shared/types';

export function useRosterEntryQuery(id: number) {
  return useQuery({
    queryKey: ['roster-entry', id],
    queryFn: () => fetchRosterEntry(id),
    enabled: !!id,
    throwOnError: true,
  });
}

export function useMyRosterEntriesQuery(enabled = true) {
  return useQuery({
    queryKey: ['my-roster-entries'],
    queryFn: fetchMyRosterEntries,
    enabled,
    throwOnError: true,
  });
}

export function useRostersQuery() {
  return useQuery({
    queryKey: ['rosters'],
    queryFn: fetchRosters,
    throwOnError: true,
  });
}

export function useRosterEntriesQuery(
  rosterId: number | undefined,
  page: number,
  filters: { name?: string; class?: string; gender?: string }
) {
  return useQuery<PaginatedResponse<RosterEntryData>>({
    queryKey: ['roster-entries', rosterId, page, filters],
    queryFn: () => fetchRosterEntries(rosterId!, page, filters),
    enabled: !!rosterId,
    throwOnError: true,
  });
}

export function useSendRosterApplication(id: number) {
  return useMutation({
    mutationFn: (message: string) => postRosterApplication(id, message),
  });
}
