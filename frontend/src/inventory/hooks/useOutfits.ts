/**
 * Outfit react-query hooks.
 *
 * Cache key shape:
 *   ["outfits", characterSheetId]      — list of outfits for a sheet
 *   ["outfit", outfitId]               — single outfit detail
 *   ["outfit-slots", outfitId]         — slots belonging to one outfit
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createOutfit,
  createOutfitSlot,
  deleteOutfit,
  deleteOutfitSlot,
  getOutfit,
  listOutfitSlots,
  listOutfits,
  updateOutfit,
} from '../api';
import type { CreateOutfitPayload, CreateOutfitSlotPayload, UpdateOutfitPayload } from '../types';

export const outfitKeys = {
  all: ['outfits'] as const,
  list: (characterSheetId: number) => ['outfits', characterSheetId] as const,
  detail: (id: number) => ['outfit', id] as const,
  slots: (outfitId: number) => ['outfit-slots', outfitId] as const,
};

export function useOutfits(characterSheetId: number | undefined) {
  return useQuery({
    queryKey: outfitKeys.list(characterSheetId ?? -1),
    queryFn: () => listOutfits(characterSheetId as number),
    enabled: characterSheetId != null,
    throwOnError: true,
  });
}

export function useOutfit(id: number | undefined) {
  return useQuery({
    queryKey: outfitKeys.detail(id ?? -1),
    queryFn: () => getOutfit(id as number),
    enabled: id != null,
    throwOnError: true,
  });
}

export function useOutfitSlots(outfitId: number | undefined) {
  return useQuery({
    queryKey: outfitKeys.slots(outfitId ?? -1),
    queryFn: () => listOutfitSlots(outfitId as number),
    enabled: outfitId != null,
    throwOnError: true,
  });
}

export function useCreateOutfit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateOutfitPayload) => createOutfit(payload),
    onSuccess: (_outfit, variables) => {
      void qc.invalidateQueries({ queryKey: outfitKeys.list(variables.character_sheet) });
    },
  });
}

export function useUpdateOutfit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateOutfitPayload }) =>
      updateOutfit(id, payload),
    onSuccess: (_outfit, variables) => {
      void qc.invalidateQueries({ queryKey: outfitKeys.detail(variables.id) });
      void qc.invalidateQueries({ queryKey: outfitKeys.all });
    },
  });
}

export function useDeleteOutfit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number; characterSheetId: number }) => deleteOutfit(id),
    onSuccess: (_void, variables) => {
      void qc.invalidateQueries({ queryKey: outfitKeys.list(variables.characterSheetId) });
      void qc.removeQueries({ queryKey: outfitKeys.detail(variables.id) });
    },
  });
}

export function useCreateOutfitSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateOutfitSlotPayload) => createOutfitSlot(payload),
    onSuccess: (_slot, variables) => {
      void qc.invalidateQueries({ queryKey: outfitKeys.slots(variables.outfit) });
      void qc.invalidateQueries({ queryKey: outfitKeys.detail(variables.outfit) });
    },
  });
}

export function useDeleteOutfitSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number; outfitId: number }) => deleteOutfitSlot(id),
    onSuccess: (_void, variables) => {
      void qc.invalidateQueries({ queryKey: outfitKeys.slots(variables.outfitId) });
      void qc.invalidateQueries({ queryKey: outfitKeys.detail(variables.outfitId) });
    },
  });
}
