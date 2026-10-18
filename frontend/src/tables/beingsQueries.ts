/**
 * React Query hooks for the Beings tab (#4333 slice 4).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './beingsApi';
import type {
  StewardAnswerWriteBody,
  StewardPledgeWriteBody,
  StewardSacrificeLineWriteBody,
  StewardSendBody,
} from './types';

const ROOT = ['tables', 'beings'] as const;

export const beingsKeys = {
  all: ROOT,
  beings: (tableId: number) => [...ROOT, 'list', tableId] as const,
  answers: (beingId: number) => [...ROOT, 'answers', beingId] as const,
  prompts: (tableId: number) => [...ROOT, 'prompts', tableId] as const,
};

export function useStewardedBeings(tableId: number) {
  return useQuery({
    queryKey: beingsKeys.beings(tableId),
    queryFn: () => api.getStewardedBeings(tableId),
    enabled: tableId > 0,
  });
}

export function useStewardAnswers(beingId: number) {
  return useQuery({
    queryKey: beingsKeys.answers(beingId),
    queryFn: () => api.getStewardAnswers(beingId),
    enabled: beingId > 0,
  });
}

export function useStewardPrompts(tableId: number) {
  return useQuery({
    queryKey: beingsKeys.prompts(tableId),
    queryFn: () => api.getStewardPrompts(tableId),
    enabled: tableId > 0,
  });
}

function useInvalidateBeings() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: beingsKeys.all }).catch(() => {});
  };
}

export function useSavePledge() {
  const invalidate = useInvalidateBeings();
  return useMutation({
    mutationFn: ({ body, pledgeId }: { body: StewardPledgeWriteBody; pledgeId?: number }) =>
      api.savePledge(body, pledgeId),
    onSuccess: invalidate,
  });
}

export function useSaveAnswer() {
  const invalidate = useInvalidateBeings();
  return useMutation({
    mutationFn: ({ body, answerId }: { body: StewardAnswerWriteBody; answerId?: number }) =>
      api.saveAnswer(body, answerId),
    onSuccess: invalidate,
  });
}

export function useSaveSacrificeLine() {
  const invalidate = useInvalidateBeings();
  return useMutation({
    mutationFn: ({ body, lineId }: { body: StewardSacrificeLineWriteBody; lineId?: number }) =>
      api.saveSacrificeLine(body, lineId),
    onSuccess: invalidate,
  });
}

export function useSendStewardAnswer() {
  const invalidate = useInvalidateBeings();
  return useMutation({
    mutationFn: ({ promptId, body }: { promptId: number; body: StewardSendBody }) =>
      api.sendStewardAnswer(promptId, body),
    onSuccess: invalidate,
  });
}

export function useDismissStewardPrompt() {
  const invalidate = useInvalidateBeings();
  return useMutation({
    mutationFn: (promptId: number) => api.dismissStewardPrompt(promptId),
    onSuccess: invalidate,
  });
}
