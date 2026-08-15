/**
 * React Query hooks for the travel system (#2352).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DispatchResult } from '@/combat/types';
import {
  fetchHubs,
  fetchMethods,
  fetchVoyages,
  fetchPendingInvites,
  dispatchVoyageAction,
} from './api';

export const TRAVEL_KEYS = {
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

/**
 * `dispatchVoyageAction` resolves through `postDispatchAction` — the dispatch
 * endpoint returns HTTP 200 even for a business-rule refusal (e.g. "no route
 * to that hub", "already in transit"), signalled only by `success: false`
 * (see `DispatchResult`). Every hook below must check it before invalidating
 * — otherwise a rejected voyage action refetches as if it landed and the
 * player never sees why it was refused (#3155).
 */
function toastAndInvalidate(
  qc: ReturnType<typeof useQueryClient>,
  keys: readonly (readonly string[])[]
) {
  return ({ message, success }: DispatchResult) => {
    if (success === false) {
      toast.error(message);
      return;
    }
    toast.success(message);
    for (const key of keys) {
      qc.invalidateQueries({ queryKey: key });
    }
  };
}

function onDispatchError(error: Error) {
  toast.error(error.message);
}

export function useStartVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { destination_id: number; travel_method_id: number }) =>
      dispatchVoyageAction(characterId, 'start_voyage', kwargs),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useInviteToVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { target_persona_id: number }) =>
      dispatchVoyageAction(characterId, 'invite_to_voyage', kwargs),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useRespondVoyageInvite(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kwargs: { invite_id: number; accept: boolean }) =>
      dispatchVoyageAction(characterId, 'respond_voyage_invite', kwargs),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.invites, TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useDepartVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'depart_voyage', {}),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useAdvanceVoyageLeg(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'advance_voyage_leg', {}),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useCompleteVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'complete_voyage', {}),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}

export function useAbandonVoyage(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dispatchVoyageAction(characterId, 'abandon_voyage', {}),
    onSuccess: toastAndInvalidate(qc, [TRAVEL_KEYS.voyages]),
    onError: onDispatchError,
  });
}
