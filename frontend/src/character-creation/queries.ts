/**
 * Character Creation React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addToRoster,
  canCreateCharacter,
  createDraft,
  createFamily,
  createFamilyMember,
  deleteDraft,
  getAffinities,
  getAnimaRitualTypes,
  getBeginnings,
  getBuilds,
  getCGPointBudget,
  getDraft,
  getDraftCGPoints,
  getFamilies,
  getFamiliesWithOpenPositions,
  getFamilyTree,
  getFormOptions,
  getGenders,
  getGift,
  getGifts,
  getHeightBands,
  getPaths,
  getPathSkillSuggestions,
  getResonances,
  getSkillPointBudget,
  getSkillsWithSpecializations,
  getSpecies,
  getStartingAreas,
  getStatDefinitions,
  submitDraft,
  updateDraft,
} from './api';
import type { CharacterDraftUpdate } from './types';

export const characterCreationKeys = {
  all: ['character-creation'] as const,
  startingAreas: () => [...characterCreationKeys.all, 'starting-areas'] as const,
  beginnings: (areaId: number) => [...characterCreationKeys.all, 'beginnings', areaId] as const,
  genders: () => [...characterCreationKeys.all, 'genders'] as const,
  species: () => [...characterCreationKeys.all, 'species'] as const,
  paths: () => [...characterCreationKeys.all, 'paths'] as const,
  cgBudget: () => [...characterCreationKeys.all, 'cg-budget'] as const,
  draftCGPoints: (draftId: number) =>
    [...characterCreationKeys.all, 'draft-cg-points', draftId] as const,
  families: (areaId: number) => [...characterCreationKeys.all, 'families', areaId] as const,
  familiesWithOpenPositions: (areaId?: number) =>
    [...characterCreationKeys.all, 'families-open', areaId] as const,
  familyTree: (familyId: number) =>
    [...characterCreationKeys.all, 'family-tree', familyId] as const,
  draft: () => [...characterCreationKeys.all, 'draft'] as const,
  canCreate: () => [...characterCreationKeys.all, 'can-create'] as const,
  heightBands: () => [...characterCreationKeys.all, 'height-bands'] as const,
  builds: () => [...characterCreationKeys.all, 'builds'] as const,
  formOptions: (speciesId: number) =>
    [...characterCreationKeys.all, 'form-options', speciesId] as const,
  statDefinitions: () => [...characterCreationKeys.all, 'stat-definitions'] as const,
  // Magic system keys
  affinities: () => [...characterCreationKeys.all, 'affinities'] as const,
  resonances: () => [...characterCreationKeys.all, 'resonances'] as const,
  gifts: () => [...characterCreationKeys.all, 'gifts'] as const,
  gift: (giftId: number) => [...characterCreationKeys.all, 'gift', giftId] as const,
  animaRitualTypes: () => [...characterCreationKeys.all, 'anima-ritual-types'] as const,
  // Skills system keys
  skills: () => [...characterCreationKeys.all, 'skills'] as const,
  skillBudget: () => [...characterCreationKeys.all, 'skill-budget'] as const,
  pathSkillSuggestions: (pathId: number) =>
    [...characterCreationKeys.all, 'path-skill-suggestions', pathId] as const,
};

export function useStartingAreas() {
  return useQuery({
    queryKey: characterCreationKeys.startingAreas(),
    queryFn: getStartingAreas,
  });
}

export function useBeginnings(areaId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.beginnings(areaId!),
    queryFn: () => getBeginnings(areaId!),
    enabled: !!areaId,
  });
}

export function useGenders() {
  return useQuery({
    queryKey: characterCreationKeys.genders(),
    queryFn: getGenders,
  });
}

export function useSpecies() {
  return useQuery({
    queryKey: characterCreationKeys.species(),
    queryFn: getSpecies,
  });
}

export function usePaths() {
  return useQuery({
    queryKey: characterCreationKeys.paths(),
    queryFn: getPaths,
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

// CG Points hooks
export function useCGPointBudget() {
  return useQuery({
    queryKey: characterCreationKeys.cgBudget(),
    queryFn: getCGPointBudget,
  });
}

export function useDraftCGPoints(draftId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.draftCGPoints(draftId!),
    queryFn: () => getDraftCGPoints(draftId!),
    enabled: !!draftId,
  });
}

// NEW: Family Tree hooks
export function useFamiliesWithOpenPositions(areaId?: number) {
  return useQuery({
    queryKey: characterCreationKeys.familiesWithOpenPositions(areaId),
    queryFn: () => getFamiliesWithOpenPositions(areaId),
  });
}

export function useFamilyTree(familyId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.familyTree(familyId!),
    queryFn: () => getFamilyTree(familyId!),
    enabled: !!familyId,
  });
}

export function useCreateFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createFamily,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.all });
    },
  });
}

export function useCreateFamilyMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createFamilyMember,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.all });
    },
  });
}

// NEW: Height Bands and Builds hooks for Appearance stage
export function useHeightBands() {
  return useQuery({
    queryKey: characterCreationKeys.heightBands(),
    queryFn: getHeightBands,
  });
}

export function useBuilds() {
  return useQuery({
    queryKey: characterCreationKeys.builds(),
    queryFn: getBuilds,
  });
}

export function useFormOptions(speciesId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.formOptions(speciesId!),
    queryFn: () => getFormOptions(speciesId!),
    enabled: !!speciesId,
  });
}

// Stat definitions hook for Attributes stage
export function useStatDefinitions() {
  return useQuery({
    queryKey: characterCreationKeys.statDefinitions(),
    queryFn: getStatDefinitions,
  });
}

// =============================================================================
// Magic System hooks
// =============================================================================

export function useAffinities() {
  return useQuery({
    queryKey: characterCreationKeys.affinities(),
    queryFn: getAffinities,
  });
}

export function useResonances() {
  return useQuery({
    queryKey: characterCreationKeys.resonances(),
    queryFn: getResonances,
  });
}

export function useGifts() {
  return useQuery({
    queryKey: characterCreationKeys.gifts(),
    queryFn: getGifts,
  });
}

export function useGift(giftId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.gift(giftId!),
    queryFn: () => getGift(giftId!),
    enabled: !!giftId,
  });
}

export function useAnimaRitualTypes() {
  return useQuery({
    queryKey: characterCreationKeys.animaRitualTypes(),
    queryFn: getAnimaRitualTypes,
  });
}

// =============================================================================
// Skills System hooks
// =============================================================================

/**
 * Get all skills with their specializations.
 */
export function useSkills() {
  return useQuery({
    queryKey: characterCreationKeys.skills(),
    queryFn: getSkillsWithSpecializations,
  });
}

/**
 * Get skill point budget configuration.
 */
export function useSkillPointBudget() {
  return useQuery({
    queryKey: characterCreationKeys.skillBudget(),
    queryFn: getSkillPointBudget,
  });
}

/**
 * Get skill suggestions for a specific path.
 */
export function usePathSkillSuggestions(pathId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.pathSkillSuggestions(pathId!),
    queryFn: () => getPathSkillSuggestions(pathId!),
    enabled: !!pathId,
  });
}
