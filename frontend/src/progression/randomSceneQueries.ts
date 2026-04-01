/**
 * API functions and React Query hooks for random scene targets.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { useAccount } from '@/store/hooks';

export interface RandomSceneTarget {
  id: number;
  target_character_name: string;
  slot_number: number;
  claimed: boolean;
  claimed_at: string | null;
  first_time: boolean;
  rerolled: boolean;
}

interface PaginatedResponse<T> {
  results: T[];
}

async function fetchRandomSceneTargets(): Promise<RandomSceneTarget[]> {
  const res = await apiFetch('/api/progression/random-scenes/');
  if (!res.ok) {
    throw new Error('Failed to load random scene targets');
  }
  const data: PaginatedResponse<RandomSceneTarget> = await res.json();
  return data.results;
}

async function claimTarget(targetId: number): Promise<RandomSceneTarget> {
  const res = await apiFetch(`/api/progression/random-scenes/${targetId}/claim/`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to claim target');
  }
  return res.json();
}

async function rerollTarget(targetId: number): Promise<RandomSceneTarget> {
  const res = await apiFetch(`/api/progression/random-scenes/${targetId}/reroll/`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to reroll target');
  }
  return res.json();
}

export function useRandomSceneTargetsQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['random-scene-targets'],
    queryFn: fetchRandomSceneTargets,
    enabled: !!account,
  });
}

export function useClaimTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: claimTarget,
    onSuccess: (updatedTarget) => {
      queryClient.setQueryData<RandomSceneTarget[]>(['random-scene-targets'], (old) => {
        if (!old) return [updatedTarget];
        return old.map((t) => (t.id === updatedTarget.id ? updatedTarget : t));
      });
    },
  });
}

export function useRerollTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: rerollTarget,
    onSuccess: (updatedTarget) => {
      queryClient.setQueryData<RandomSceneTarget[]>(['random-scene-targets'], (old) => {
        if (!old) return [updatedTarget];
        return old.map((t) => (t.id === updatedTarget.id ? updatedTarget : t));
      });
    },
  });
}
