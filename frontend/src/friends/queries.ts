/** React Query hooks for the OOC friends list (#1727). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { addFriend, listFriends, removeFriend } from './api';
import type { AddFriendPayload } from './api';

export const friendKeys = { list: ['friends'] as const };

export function useFriendsQuery() {
  return useQuery({ queryKey: friendKeys.list, queryFn: listFriends });
}

export function useAddFriendMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddFriendPayload) => addFriend(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: friendKeys.list }),
  });
}

export function useRemoveFriendMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => removeFriend(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: friendKeys.list }),
  });
}
