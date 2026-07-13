/**
 * React Query hooks for the travel system (#2352).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchHubs,
  fetchMethods,
  fetchVoyages,
  fetchPendingInvites,
  dispatchVoyageAction,
} from './api';

const TRAVEL_KEYS = {
  hubs: ['travel', 'hubs'] as const,
  methods: ['travel', 'methods'] as const,
  voyages: ['travel', 'voyages'] as const,
  invites: ['travel', 'invites'] as const,
};

export function useTravelHubs() {
  return useQuery({ queryKey: TRAVEL_KEYS.hubs, queryFn: fetchHubs });
}

export function useTravelMethods() {
  return useQuery({ queryKey: TRAVEL_KEYS.methods, queryFn: fetchMethods });
}

export function useVoyages() {
  return useQuery({ queryKey: TRAVEL_KEYS.voyages, queryFn: fetchVoyages });
}

export function usePendingVoyageInvites() {
  return useQuery({ queryKey: TRAVEL_KEYS.invites, queryFn: fetchPendingInvites });
}

export function useStartVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { destination_id: number; travel_method_id: number }) =>
      dispatchVoyageAction(characterId, 'start_voyage', kwargs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useInviteToVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { target_persona_id: number }) =>
      dispatchVoyageAction(characterId, 'invite_to_voyage', kwargs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useRespondVoyageInvite(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { invite_id: number; accept: boolean }) =>
      dispatchVoyageAction(characterId, 'respond_voyage_invite', kwargs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.invites });
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useDepartVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'depart_voyage', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useAdvanceVoyageLeg(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'advance_voyage_leg', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useCompleteVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'complete_voyage', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}

export function useAbandonVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'abandon_voyage', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TRAVEL_KEYS.voyages });
    },
  });
}
