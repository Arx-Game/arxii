/**
 * React Query hooks for the live answer panel (#4333 slice 5).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './liveAnswerApi';
import { gmPromptKeys } from './gmPromptQueries';
import { sceneFeedSceneKey } from '@/scenes/sceneFeedCache';

export const liveAnswerKeys = {
  prompt: (promptId: number) => ['live-answers', promptId] as const,
};

export function useLivePrompt(promptId: number, enabled: boolean) {
  return useQuery({
    queryKey: liveAnswerKeys.prompt(promptId),
    queryFn: () => api.getLivePrompt(promptId),
    enabled,
  });
}

/** After a send or a dismiss the row is closed server-side: refetch the queue. */
function useRefreshQueue(sceneId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: gmPromptKeys.scene(sceneId) }).catch(() => {});
    queryClient.invalidateQueries({ queryKey: sceneFeedSceneKey(sceneId) }).catch(() => {});
  };
}

export function useSendLiveAnswer(sceneId: string) {
  const refresh = useRefreshQueue(sceneId);
  return useMutation({
    mutationFn: ({ promptId, body }: { promptId: number; body: Partial<api.LiveSendBody> }) =>
      api.sendLiveAnswer(promptId, body),
    onSuccess: refresh,
    // A refused send usually means the prompt moved on (another GM answered, the
    // limit was reached): refetch so the queue stops offering a stale row.
    onError: refresh,
  });
}

export function useDismissLivePrompt(sceneId: string) {
  const refresh = useRefreshQueue(sceneId);
  return useMutation({
    mutationFn: (promptId: number) => api.dismissLivePrompt(promptId),
    onSuccess: refresh,
    onError: refresh,
  });
}
