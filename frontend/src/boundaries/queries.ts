import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchContentThemes,
  fetchPlayerBoundaries,
  createPlayerBoundary,
  updatePlayerBoundary,
  deletePlayerBoundary,
  fetchTreasuredSubjects,
  createTreasuredSubject,
  updateTreasuredSubject,
  deleteTreasuredSubject,
  fetchTreasuredSignoffs,
  grantTreasuredSignoff,
  withdrawTreasuredSignoff,
  fetchSceneLinesAndVeils,
} from './api';
import type {
  PatchedPlayerBoundaryRequest,
  PatchedTreasuredSubjectRequest,
  PlayerBoundaryRequest,
  TreasuredSignoffRequest,
  TreasuredSubjectRequest,
} from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const boundariesKeys = {
  contentThemes: () => ['boundaries', 'content-themes'] as const,
  playerBoundaries: () => ['boundaries', 'player-boundaries'] as const,
  treasuredSubjects: (tenureId: number) => ['boundaries', 'treasured-subjects', tenureId] as const,
  treasuredSignoffs: (params: { beat?: number; treasured_subject?: number }) =>
    [
      'boundaries',
      'treasured-signoffs',
      params.beat ?? null,
      params.treasured_subject ?? null,
    ] as const,
  sceneLinesAndVeils: (sceneId: string | number, tenureId: number) =>
    ['boundaries', 'scene-lines-and-veils', sceneId, tenureId] as const,
};

// ---------------------------------------------------------------------------
// Content themes
// ---------------------------------------------------------------------------

export function useContentThemes() {
  return useQuery({
    queryKey: boundariesKeys.contentThemes(),
    queryFn: fetchContentThemes,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// PlayerBoundary
// ---------------------------------------------------------------------------

export function usePlayerBoundaries() {
  return useQuery({
    queryKey: boundariesKeys.playerBoundaries(),
    queryFn: fetchPlayerBoundaries,
    throwOnError: true,
  });
}

export function useCreatePlayerBoundary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PlayerBoundaryRequest) => createPlayerBoundary(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.playerBoundaries() });
    },
  });
}

export function useUpdatePlayerBoundary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PatchedPlayerBoundaryRequest }) =>
      updatePlayerBoundary(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.playerBoundaries() });
    },
  });
}

export function useDeletePlayerBoundary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deletePlayerBoundary(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.playerBoundaries() });
    },
  });
}

// ---------------------------------------------------------------------------
// TreasuredSubject
// ---------------------------------------------------------------------------

export function useTreasuredSubjects(tenureId: number | undefined) {
  return useQuery({
    queryKey: boundariesKeys.treasuredSubjects(tenureId!),
    queryFn: () => fetchTreasuredSubjects(tenureId!),
    enabled: !!tenureId,
    throwOnError: true,
  });
}

export function useCreateTreasuredSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TreasuredSubjectRequest) => createTreasuredSubject(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.treasuredSubjects(data.owner) });
    },
  });
}

export function useUpdateTreasuredSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
      tenureId,
    }: {
      id: number;
      body: PatchedTreasuredSubjectRequest;
      tenureId: number;
    }) => updateTreasuredSubject(id, body).then((updated) => ({ updated, tenureId })),
    onSuccess: ({ tenureId }) => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.treasuredSubjects(tenureId) });
    },
  });
}

export function useDeleteTreasuredSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number; tenureId: number }) => deleteTreasuredSubject(id),
    onSuccess: (_data, { tenureId }) => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.treasuredSubjects(tenureId) });
    },
  });
}

// ---------------------------------------------------------------------------
// TreasuredSignoff
// ---------------------------------------------------------------------------

export function useTreasuredSignoffs(params: { beat?: number; treasured_subject?: number }) {
  return useQuery({
    queryKey: boundariesKeys.treasuredSignoffs(params),
    queryFn: () => fetchTreasuredSignoffs(params),
    enabled: params.beat != null || params.treasured_subject != null,
    throwOnError: true,
  });
}

export function useGrantTreasuredSignoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TreasuredSignoffRequest) => grantTreasuredSignoff(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: boundariesKeys.treasuredSignoffs({ beat: data.beat }),
      });
    },
  });
}

export function useWithdrawTreasuredSignoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number; beat: number }) => withdrawTreasuredSignoff(id),
    onSuccess: (_data, { beat }) => {
      queryClient.invalidateQueries({ queryKey: boundariesKeys.treasuredSignoffs({ beat }) });
    },
  });
}

// ---------------------------------------------------------------------------
// Scene "lines & veils" aggregate
// ---------------------------------------------------------------------------

export function useSceneLinesAndVeils(
  sceneId: string | number | undefined,
  tenureId: number | undefined
) {
  return useQuery({
    queryKey: boundariesKeys.sceneLinesAndVeils(sceneId!, tenureId!),
    queryFn: () => fetchSceneLinesAndVeils(sceneId!, tenureId!),
    enabled: !!sceneId && !!tenureId,
    throwOnError: true,
  });
}
