import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { dispatchStoryRoomAction, fetchMyStoryGrants } from './api';
import type { StoryRoomActionKey } from './types';

/** Hierarchical key namespace with matchable prefixes (project convention). */
export const storyRoomsKeys = {
  all: ['story-rooms'] as const,
  myGrants: () => [...storyRoomsKeys.all, 'my-grants'] as const,
};

export function useMyStoryGrantsQuery() {
  return useQuery({
    queryKey: storyRoomsKeys.myGrants(),
    queryFn: fetchMyStoryGrants,
    staleTime: 15_000,
  });
}

export interface StoryRoomActionInput {
  characterId: number;
  key: StoryRoomActionKey;
  kwargs: Record<string, unknown>;
}

/**
 * Dispatch `join_story_room`/`leave_story_room` by registry key, toast the
 * action's message, refresh the grants list. A `success: false` dispatch (a
 * business-rule refusal — HTTP 200, see `DispatchResult` in `./api`) toasts an
 * error and skips the cache invalidation instead, so a refused action never
 * looks like it landed — mirrors `useStoryBuilderAction`
 * (`frontend/src/story-builder/queries.ts`).
 */
export function useStoryRoomAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ characterId, key, kwargs }: StoryRoomActionInput) =>
      dispatchStoryRoomAction(characterId, key, kwargs),
    onSuccess: ({ message, success }) => {
      if (success === false) {
        toast.error(message);
        return;
      }
      toast.success(message);
      queryClient.invalidateQueries({ queryKey: storyRoomsKeys.myGrants() });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}
