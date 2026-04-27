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
  return useQuery({
    queryKey: narrativeKeys.myMessages(filters),
    queryFn: () => getMyMessages(filters),
    throwOnError: true,
  });
}

export function useAcknowledgeDelivery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acknowledgeDelivery,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: narrativeKeys.all });
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
      void queryClient.invalidateQueries({ queryKey: gemitKeys.all });
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
      void queryClient.invalidateQueries({ queryKey: narrativeKeys.storyMutes() });
    },
  });
}

export function useUnmuteStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (muteId: number) => unmuteStory(muteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: narrativeKeys.storyMutes() });
    },
  });
}
