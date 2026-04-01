/**
 * API functions and React Query hooks for the weekly vote system.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';

// --- Types ---

export type VoteTargetType = 'interaction' | 'scene_participation' | 'journal';

export interface VoteBudget {
  base_votes: number;
  scene_bonus_votes: number;
  votes_spent: number;
  votes_remaining: number;
}

export interface WeeklyVote {
  id: number;
  target_type: VoteTargetType;
  target_id: number;
  target_name: string;
  created_at: string;
}

interface CastVoteResponse {
  vote: WeeklyVote;
  budget: VoteBudget;
}

// --- API functions ---

export async function fetchVoteBudget(): Promise<VoteBudget> {
  const res = await apiFetch('/api/progression/votes/budget/');
  if (!res.ok) throw new Error('Failed to load vote budget');
  return res.json();
}

export async function fetchMyVotes(): Promise<WeeklyVote[]> {
  const res = await apiFetch('/api/progression/votes/');
  if (!res.ok) throw new Error('Failed to load votes');
  return res.json();
}

export async function castVote(
  targetType: VoteTargetType,
  targetId: number
): Promise<CastVoteResponse> {
  const res = await apiFetch('/api/progression/votes/', {
    method: 'POST',
    body: JSON.stringify({ target_type: targetType, target_id: targetId }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to cast vote');
  }
  return res.json();
}

export async function removeVote(voteId: number): Promise<void> {
  const res = await apiFetch(`/api/progression/votes/${voteId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to remove vote');
}

// --- Query keys ---

export const voteKeys = {
  budget: ['vote-budget'] as const,
  myVotes: ['my-votes'] as const,
};

// --- Hooks ---

export function useVoteBudgetQuery() {
  return useQuery({
    queryKey: voteKeys.budget,
    queryFn: fetchVoteBudget,
  });
}

export function useMyVotesQuery() {
  return useQuery({
    queryKey: voteKeys.myVotes,
    queryFn: fetchMyVotes,
  });
}

export function useCastVoteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetType, targetId }: { targetType: VoteTargetType; targetId: number }) =>
      castVote(targetType, targetId),
    onSuccess: (data) => {
      queryClient.setQueryData<VoteBudget>(voteKeys.budget, data.budget);
      queryClient.setQueryData<WeeklyVote[]>(voteKeys.myVotes, (old) => {
        return old ? [...old, data.vote] : [data.vote];
      });
    },
  });
}

export function useRemoveVoteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (voteId: number) => removeVote(voteId),
    onSuccess: (_, voteId) => {
      queryClient.setQueryData<WeeklyVote[]>(voteKeys.myVotes, (old) => {
        return old ? old.filter((v) => v.id !== voteId) : [];
      });
      queryClient.invalidateQueries({ queryKey: voteKeys.budget });
    },
  });
}
