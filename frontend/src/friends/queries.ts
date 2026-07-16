/** React Query hooks for the OOC friends list (#1727) and rival declarations (#2170). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  addFriend,
  declareRival,
  listFriends,
  listRivals,
  removeFriend,
  withdrawRival,
} from './api';
import type { AddFriendPayload, DeclareRivalPayload } from './api';

export const friendKeys = { list: ['friends'] as const };
export const rivalKeys = { list: ['rivals'] as const };

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

export function useRivalsQuery() {
  return useQuery({ queryKey: rivalKeys.list, queryFn: listRivals });
}

export function useDeclareRivalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeclareRivalPayload) => declareRival(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: rivalKeys.list }),
  });
}

export function useWithdrawRivalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => withdrawRival(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: rivalKeys.list }),
  });
}
