/** React Query hooks for the Block/Mute controls (#1278). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createBlock, createMute, listBlocks, listMutes, shareBlock, unblock, unmute } from './api';
import type { BlockCreateRequest, MuteCreateRequest } from './types';

export const socialKeys = {
  blocks: () => ['social', 'blocks'] as const,
  mutes: () => ['social', 'mutes'] as const,
};

export function useBlocks() {
  return useQuery({ queryKey: socialKeys.blocks(), queryFn: listBlocks });
}

export function useMutes() {
  return useQuery({ queryKey: socialKeys.mutes(), queryFn: listMutes });
}

export function useCreateBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BlockCreateRequest) => createBlock(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: socialKeys.blocks() }).catch(() => {});
    },
  });
}

export function useUnblock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unblock(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: socialKeys.blocks() }).catch(() => {});
    },
  });
}

export function useShareBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => shareBlock(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: socialKeys.blocks() }).catch(() => {});
    },
  });
}

export function useCreateMute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: MuteCreateRequest) => createMute(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: socialKeys.mutes() }).catch(() => {});
    },
  });
}

export function useUnmute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unmute(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: socialKeys.mutes() }).catch(() => {});
    },
  });
}
