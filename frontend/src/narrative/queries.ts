/**
 * Narrative React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  acknowledgeDelivery,
  broadcastGemit,
  getGemits,
  getMyMessages,
  getStoryMutes,
  muteStory,
  unmuteStory,
} from './api';
import { useAppSelector } from '@/store/hooks';
import type {
  BroadcastGemitBody,
  GemitListParams,
  MyMessagesQueryParams,
  UserStoryMuteCreateBody,
} from './types';

export const narrativeKeys = {
  all: ['narrative'] as const,
  myMessages: (filters?: MyMessagesQueryParams) =>
    [...narrativeKeys.all, 'my-messages', filters] as const,
  gemits: (params?: GemitListParams) => [...narrativeKeys.all, 'gemits', params] as const,
  storyMutes: () => [...narrativeKeys.all, 'story-mutes'] as const,
};

// Alias for the gemit list root — used by ChatWindow to invalidate on gemit push.
export const gemitKeys = {
  all: ['narrative', 'gemits'] as const,
};

export function useMyMessages(filters?: MyMessagesQueryParams) {
  // The badge that consumes this hook is rendered unconditionally in the
  // global Header, so without an auth guard the query fires on the login
  // page itself, gets 403, and `throwOnError: true` blows the page up via
  // the error boundary. Guard on the cached account so unauthenticated
  // page loads stay quiet.
  const account = useAppSelector((s) => s.auth.account);
  return useQuery({
    queryKey: narrativeKeys.myMessages(filters),
    queryFn: () => getMyMessages(filters),
    enabled: !!account,
    throwOnError: true,
  });
}

export function useAcknowledgeDelivery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acknowledgeDelivery,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: narrativeKeys.all }).catch(() => {});
    },
  });
}

export function useUnreadNarrativeCount() {
  const { data } = useMyMessages({ acknowledged: false });
  return data?.count ?? 0;
}

// ---------------------------------------------------------------------------
// Gemit hooks (Wave 8)
// ---------------------------------------------------------------------------

export function useGemits(params?: GemitListParams) {
  return useQuery({
    queryKey: narrativeKeys.gemits(params),
    queryFn: () => getGemits(params),
    throwOnError: true,
  });
}

export function useBroadcastGemit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BroadcastGemitBody) => broadcastGemit(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gemitKeys.all }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// UserStoryMute hooks (Wave 9)
// ---------------------------------------------------------------------------

export function useStoryMutes() {
  return useQuery({
    queryKey: narrativeKeys.storyMutes(),
    queryFn: getStoryMutes,
    throwOnError: true,
  });
}

export function useMuteStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UserStoryMuteCreateBody) => muteStory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: narrativeKeys.storyMutes() }).catch(() => {});
    },
  });
}

export function useUnmuteStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (muteId: number) => unmuteStory(muteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: narrativeKeys.storyMutes() }).catch(() => {});
    },
  });
}
