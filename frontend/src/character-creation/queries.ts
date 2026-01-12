/**
 * Character Creation React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addToRoster,
  canCreateCharacter,
  createDraft,
  deleteDraft,
  getDraft,
  getFamilies,
  getSpecies,
  getStartingAreas,
  submitDraft,
  updateDraft,
} from './api';
import type { CharacterDraftUpdate } from './types';

export const characterCreationKeys = {
  all: ['character-creation'] as const,
  startingAreas: () => [...characterCreationKeys.all, 'starting-areas'] as const,
  species: (areaId: number, heritageId?: number) =>
    [...characterCreationKeys.all, 'species', areaId, heritageId] as const,
  families: (areaId: number) => [...characterCreationKeys.all, 'families', areaId] as const,
  draft: () => [...characterCreationKeys.all, 'draft'] as const,
  canCreate: () => [...characterCreationKeys.all, 'can-create'] as const,
};

export function useStartingAreas() {
  return useQuery({
    queryKey: characterCreationKeys.startingAreas(),
    queryFn: getStartingAreas,
  });
}

export function useSpecies(areaId: number | undefined, heritageId?: number) {
  return useQuery({
    queryKey: characterCreationKeys.species(areaId!, heritageId),
    queryFn: () => getSpecies(areaId!, heritageId),
    enabled: !!areaId,
  });
}

export function useFamilies(areaId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.families(areaId!),
    queryFn: () => getFamilies(areaId!),
    enabled: !!areaId,
  });
}

export function useDraft() {
  return useQuery({
    queryKey: characterCreationKeys.draft(),
    queryFn: getDraft,
  });
}

export function useCanCreateCharacter() {
  return useQuery({
    queryKey: characterCreationKeys.canCreate(),
    queryFn: canCreateCharacter,
  });
}

export function useCreateDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraft,
    onSuccess: (data) => {
      queryClient.setQueryData(characterCreationKeys.draft(), data);
    },
  });
}

export function useUpdateDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: number; data: CharacterDraftUpdate }) =>
      updateDraft(draftId, data),
    onSuccess: (data) => {
      queryClient.setQueryData(characterCreationKeys.draft(), data);
    },
  });
}

export function useDeleteDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => deleteDraft(draftId),
    onSuccess: () => {
      queryClient.setQueryData(characterCreationKeys.draft(), null);
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.canCreate() });
    },
  });
}

export function useSubmitDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => submitDraft(draftId),
    onSuccess: () => {
      queryClient.setQueryData(characterCreationKeys.draft(), null);
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.canCreate() });
    },
  });
}

export function useAddToRoster() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => addToRoster(draftId),
    onSuccess: () => {
      queryClient.setQueryData(characterCreationKeys.draft(), null);
    },
  });
}
