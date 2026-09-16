import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchBeingPage,
  fetchBeingPrayers,
  fetchBeingVisions,
  fetchBeings,
  fetchCodexRows,
  fetchEditorOptions,
  fetchOverview,
  fetchRelics,
  fetchSites,
  fetchWorshipTab,
  saveBeingPage,
  searchRosterCharacters,
  sendVisionFromBeing,
  type BeingListParams,
} from './api';
import type { StaffBeingPageRequest } from './types';
import type { VisionCreate } from '@/worship/types';

export const pantheonKeys = {
  all: ['pantheon'] as const,
  list: (params: BeingListParams) => ['pantheon', 'list', params] as const,
  page: (id: number) => ['pantheon', 'page', id] as const,
  options: ['pantheon', 'options'] as const,
  tab: (id: number, tab: string) => ['pantheon', 'tab', id, tab] as const,
  roster: (name: string) => ['pantheon', 'roster', name] as const,
};

export function useBeings(params: BeingListParams) {
  return useQuery({ queryKey: pantheonKeys.list(params), queryFn: () => fetchBeings(params) });
}

export function useBeingPage(id: number | null) {
  return useQuery({
    queryKey: pantheonKeys.page(id ?? 0),
    queryFn: () => fetchBeingPage(id ?? 0),
    enabled: id !== null,
  });
}

export function useEditorOptions() {
  return useQuery({ queryKey: pantheonKeys.options, queryFn: fetchEditorOptions });
}

export function useSaveBeing(id: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (page: StaffBeingPageRequest) => saveBeingPage(id, page),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pantheonKeys.all }).catch(() => {});
    },
  });
}

export function useOverview(id: number) {
  return useQuery({ queryKey: pantheonKeys.tab(id, 'overview'), queryFn: () => fetchOverview(id) });
}

export function useWorshipTab(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'worship'),
    queryFn: () => fetchWorshipTab(id),
    enabled,
  });
}

export function useSites(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'sites'),
    queryFn: () => fetchSites(id),
    enabled,
  });
}

export function useBeingPrayers(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'prayers'),
    queryFn: () => fetchBeingPrayers(id),
    enabled,
  });
}

export function useBeingVisions(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'visions'),
    queryFn: () => fetchBeingVisions(id),
    enabled,
  });
}

export function useRelics(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'relics'),
    queryFn: () => fetchRelics(id),
    enabled,
  });
}

export function useCodexRows(id: number, enabled: boolean) {
  return useQuery({
    queryKey: pantheonKeys.tab(id, 'codex'),
    queryFn: () => fetchCodexRows(id),
    enabled,
  });
}

export function useRosterSearch(name: string) {
  return useQuery({
    queryKey: pantheonKeys.roster(name),
    queryFn: () => searchRosterCharacters(name),
    enabled: name.trim().length >= 2,
  });
}

export function useSendVisionFromBeing(beingId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VisionCreate) => sendVisionFromBeing(payload),
    onSuccess: () => {
      queryClient
        .invalidateQueries({ queryKey: pantheonKeys.tab(beingId, 'visions') })
        .catch(() => {});
      queryClient
        .invalidateQueries({ queryKey: pantheonKeys.tab(beingId, 'overview') })
        .catch(() => {});
      queryClient.invalidateQueries({ queryKey: pantheonKeys.page(beingId) }).catch(() => {});
    },
  });
}
