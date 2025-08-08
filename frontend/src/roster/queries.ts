import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchRosterEntry,
  fetchMyRosterEntries,
  fetchRosters,
  fetchRosterEntries,
  postRosterApplication,
} from './api';
import type { RosterEntryData, RosterData, CharacterData } from './types';
import type { PaginatedResponse } from '@/shared/types';

export function useRosterEntryQuery(id: RosterEntryData['id']) {
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
  rosterId: RosterData['id'] | undefined,
  page: number,
  filters: Partial<Pick<CharacterData, 'name' | 'char_class' | 'gender'>>
) {
  return useQuery<PaginatedResponse<RosterEntryData>>({
    queryKey: ['roster-entries', rosterId, page, filters],
    queryFn: () => fetchRosterEntries(rosterId!, page, filters),
    enabled: !!rosterId,
    throwOnError: true,
  });
}

export function useSendRosterApplication(id: RosterEntryData['id']) {
  return useMutation({
    mutationFn: (message: string) => postRosterApplication(id, message),
  });
}
