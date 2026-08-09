/**
 * React Query hooks for the GM adjudication toolkit's catalog pickers (#3070).
 */

import { useQuery } from '@tanstack/react-query';
import * as api from './api';

export const gmAdjudicationKeys = {
  all: ['gm-adjudication'] as const,
  checkTypes: (search: string) => [...gmAdjudicationKeys.all, 'check-types', search] as const,
  conditionTemplates: () => [...gmAdjudicationKeys.all, 'condition-templates'] as const,
  situationTemplates: () => [...gmAdjudicationKeys.all, 'situation-templates'] as const,
  challengeTemplates: () => [...gmAdjudicationKeys.all, 'challenge-templates'] as const,
  summonOffers: () => [...gmAdjudicationKeys.all, 'summon-offers'] as const,
};

/** Enabled only while the picker is open — `enabled` lets the panel defer the
 *  fetch until a GM actually opens the relevant tab. */
export function useCheckTypeCatalog(search: string, enabled: boolean) {
  return useQuery({
    queryKey: gmAdjudicationKeys.checkTypes(search),
    queryFn: () => api.getCheckTypeCatalog(search),
    enabled,
    staleTime: 30_000,
  });
}

export function useConditionTemplateCatalog(enabled: boolean) {
  return useQuery({
    queryKey: gmAdjudicationKeys.conditionTemplates(),
    queryFn: () => api.getConditionTemplateCatalog(),
    enabled,
    staleTime: 60_000,
  });
}

export function useSituationTemplateCatalog(enabled: boolean) {
  return useQuery({
    queryKey: gmAdjudicationKeys.situationTemplates(),
    queryFn: () => api.getSituationTemplateCatalog(),
    enabled,
    staleTime: 60_000,
  });
}

export function useChallengeTemplateCatalog(enabled: boolean) {
  return useQuery({
    queryKey: gmAdjudicationKeys.challengeTemplates(),
    queryFn: () => api.getChallengeTemplateCatalog(),
    enabled,
    staleTime: 60_000,
  });
}

/**
 * Poll the requesting player's pending GM summon offer(s) (#3071).
 *
 * Mirrors `useDuelChallengeInbox` (`@/combat/queries`) — 15s poll so an
 * incoming summon appears without a manual refresh.
 */
export function useSummonOfferInbox(options: { enabled?: boolean } = {}) {
  const { enabled = true } = options;
  return useQuery({
    queryKey: gmAdjudicationKeys.summonOffers(),
    queryFn: () => api.fetchSummonOfferInbox(),
    enabled,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}
