/**
 * Character Creation React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addDraftComment,
  addToRoster,
  canCreateCharacter,
  createDraft,
  createDraftAnimaRitual,
  createDraftFacetAssignment,
  createDraftGift,
  createDraftMotif,
  createDraftTechnique,
  ensureDraftMotif,
  createFamily,
  createFamilyMember,
  createGift,
  createTechnique,
  deleteDraft,
  deleteDraftFacetAssignment,
  deleteDraftGift,
  deleteDraftTechnique,
  deleteTechnique,
  getAffinities,
  getAnimaRitualTypes,
  getBeginnings,
  getBuilds,
  getCGPointBudget,
  getDraft,
  getDraftAnimaRitual,
  getDraftApplication,
  getDraftCGPoints,
  getDraftGift,
  getDraftGifts,
  getDraftMotif,
  getEffectTypes,
  getFacets,
  getFacetTree,
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
  getProjectedResonances,
  getResonanceAssociations,
  getResonances,
  getRestrictions,
  getSkillPointBudget,
  getSkillsWithSpecializations,
  getSpecies,
  getStartingAreas,
  getStatDefinitions,
  getTarotCards,
  getTechniqueStyles,
  getTraditions,
  resubmitDraft,
  selectTradition,
  submitDraftForReview,
  unsubmitDraft,
  updateDraft,
  updateDraftAnimaRitual,
  updateDraftGift,
  updateDraftMotif,
  updateDraftTechnique,
  updateTechnique,
  withdrawDraft,
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
  projectedResonances: (draftId: number) =>
    [...characterCreationKeys.all, 'projected-resonances', draftId] as const,
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
  // Build-your-own magic system keys
  techniqueStyles: () => [...characterCreationKeys.all, 'technique-styles'] as const,
  effectTypes: () => [...characterCreationKeys.all, 'effect-types'] as const,
  restrictions: (effectTypeId?: number) =>
    [...characterCreationKeys.all, 'restrictions', effectTypeId] as const,
  resonanceAssociations: (category?: string) =>
    [...characterCreationKeys.all, 'resonance-associations', category] as const,
  techniques: (giftId?: number) => [...characterCreationKeys.all, 'techniques', giftId] as const,
  // Skills system keys
  skills: () => [...characterCreationKeys.all, 'skills'] as const,
  skillBudget: () => [...characterCreationKeys.all, 'skill-budget'] as const,
  pathSkillSuggestions: (pathId: number) =>
    [...characterCreationKeys.all, 'path-skill-suggestions', pathId] as const,
  // Draft magic keys
  draftGifts: () => [...characterCreationKeys.all, 'draft-gifts'] as const,
  draftGift: (giftId: number) => [...characterCreationKeys.all, 'draft-gift', giftId] as const,
  draftMotif: () => [...characterCreationKeys.all, 'draft-motif'] as const,
  draftAnimaRitual: () => [...characterCreationKeys.all, 'draft-anima-ritual'] as const,
  // Facet keys
  facets: () => [...characterCreationKeys.all, 'facets'] as const,
  facetTree: () => [...characterCreationKeys.all, 'facet-tree'] as const,
  // Tradition keys
  traditions: (beginningId: number) =>
    [...characterCreationKeys.all, 'traditions', beginningId] as const,
  // Tarot cards key
  tarotCards: () => [...characterCreationKeys.all, 'tarot-cards'] as const,
  // Application key
  application: (draftId: number) => [...characterCreationKeys.all, 'application', draftId] as const,
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
    mutationFn: ({ draftId, submissionNotes }: { draftId: number; submissionNotes: string }) =>
      submitDraftForReview(draftId, submissionNotes),
    onSuccess: (_data, { draftId }) => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draft() });
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.application(draftId) });
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

export function useProjectedResonances(draftId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.projectedResonances(draftId!),
    queryFn: () => getProjectedResonances(draftId!),
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
// Build-Your-Own Magic System hooks
// =============================================================================

export function useTechniqueStyles() {
  return useQuery({
    queryKey: characterCreationKeys.techniqueStyles(),
    queryFn: getTechniqueStyles,
  });
}

export function useEffectTypes() {
  return useQuery({
    queryKey: characterCreationKeys.effectTypes(),
    queryFn: getEffectTypes,
  });
}

export function useRestrictions(effectTypeId?: number) {
  return useQuery({
    queryKey: characterCreationKeys.restrictions(effectTypeId),
    queryFn: () => getRestrictions(effectTypeId),
  });
}

export function useResonanceAssociations(category?: string) {
  return useQuery({
    queryKey: characterCreationKeys.resonanceAssociations(category),
    queryFn: () => getResonanceAssociations(category),
  });
}

export function useCreateGift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createGift,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.gifts() });
    },
  });
}

export function useCreateTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTechnique,
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: characterCreationKeys.techniques(data.gift),
      });
    },
  });
}

export function useUpdateTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      techniqueId,
      data,
    }: {
      techniqueId: number;
      data: Parameters<typeof updateTechnique>[1];
    }) => updateTechnique(techniqueId, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: characterCreationKeys.techniques(data.gift),
      });
    },
  });
}

export function useDeleteTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteTechnique,
    onSuccess: () => {
      // Invalidate all technique queries since we don't know the gift
      queryClient.invalidateQueries({
        queryKey: [...characterCreationKeys.all, 'techniques'],
      });
    },
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

// =============================================================================
// Draft Magic Hooks
// =============================================================================

export function useDraftGifts() {
  return useQuery({
    queryKey: characterCreationKeys.draftGifts(),
    queryFn: getDraftGifts,
  });
}

export function useDraftGift(giftId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.draftGift(giftId!),
    queryFn: () => getDraftGift(giftId!),
    enabled: !!giftId,
  });
}

export function useDraftMotif() {
  return useQuery({
    queryKey: characterCreationKeys.draftMotif(),
    queryFn: getDraftMotif,
  });
}

export function useDraftAnimaRitual() {
  return useQuery({
    queryKey: characterCreationKeys.draftAnimaRitual(),
    queryFn: getDraftAnimaRitual,
  });
}

export function useCreateDraftGift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraftGift,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useUpdateDraftGift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      giftId,
      data,
    }: {
      giftId: number;
      data: Parameters<typeof updateDraftGift>[1];
    }) => updateDraftGift(giftId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useDeleteDraftGift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDraftGift,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useCreateDraftTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraftTechnique,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useUpdateDraftTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      techniqueId,
      data,
    }: {
      techniqueId: number;
      data: Parameters<typeof updateDraftTechnique>[1];
    }) => updateDraftTechnique(techniqueId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useDeleteDraftTechnique() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDraftTechnique,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
    },
  });
}

export function useCreateDraftMotif() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraftMotif,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
    },
  });
}

export function useEnsureDraftMotif() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ensureDraftMotif,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
    },
  });
}

export function useUpdateDraftMotif() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      motifId,
      data,
    }: {
      motifId: number;
      data: Parameters<typeof updateDraftMotif>[1];
    }) => updateDraftMotif(motifId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
    },
  });
}

export function useCreateDraftAnimaRitual() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraftAnimaRitual,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftAnimaRitual() });
    },
  });
}

export function useUpdateDraftAnimaRitual() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ritualId,
      data,
    }: {
      ritualId: number;
      data: Parameters<typeof updateDraftAnimaRitual>[1];
    }) => updateDraftAnimaRitual(ritualId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftAnimaRitual() });
    },
  });
}

// =============================================================================
// Facet Hooks
// =============================================================================

export function useFacets() {
  return useQuery({
    queryKey: characterCreationKeys.facets(),
    queryFn: getFacets,
  });
}

export function useFacetTree() {
  return useQuery({
    queryKey: characterCreationKeys.facetTree(),
    queryFn: getFacetTree,
  });
}

export function useCreateDraftFacetAssignment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDraftFacetAssignment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
    },
  });
}

export function useDeleteDraftFacetAssignment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDraftFacetAssignment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
    },
  });
}

// =============================================================================
// Tarot Card Hooks
// =============================================================================

export function useTarotCards() {
  return useQuery({
    queryKey: characterCreationKeys.tarotCards(),
    queryFn: getTarotCards,
  });
}

// =============================================================================
// Traditions Hooks
// =============================================================================

export function useTraditions(beginningId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.traditions(beginningId!),
    queryFn: () => getTraditions(beginningId!),
    enabled: !!beginningId,
  });
}

export function useSelectTradition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, traditionId }: { draftId: number; traditionId: number | null }) =>
      selectTradition(draftId, traditionId),
    onSuccess: (_data, { draftId }) => {
      // Invalidate draft + draft magic data since tradition template pre-fills magic
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draft() });
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftGifts() });
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftMotif() });
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftAnimaRitual() });
      // Selecting a tradition may auto-add a required distinction, affecting CG points
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftCGPoints(draftId) });
    },
  });
}

// =============================================================================
// Application Hooks
// =============================================================================

export function useDraftApplication(draftId: number | undefined) {
  return useQuery({
    queryKey: characterCreationKeys.application(draftId!),
    queryFn: () => getDraftApplication(draftId!),
    enabled: !!draftId,
  });
}

export function useUnsubmitDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => unsubmitDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.all });
    },
  });
}

export function useResubmitDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, comment }: { draftId: number; comment?: string }) =>
      resubmitDraft(draftId, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.all });
    },
  });
}

export function useWithdrawDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: number) => withdrawDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterCreationKeys.all });
    },
  });
}

export function useAddDraftComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, text }: { draftId: number; text: string }) =>
      addDraftComment(draftId, text),
    onSuccess: (_data, { draftId }) => {
      queryClient.invalidateQueries({
        queryKey: characterCreationKeys.application(draftId),
      });
    },
  });
}
