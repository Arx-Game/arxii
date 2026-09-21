/**
 * React Query hooks for ties (#3957).
 *
 * Every write invalidates BOTH the tie prefix and the character-sheet prefix: a label,
 * an awareness step, a tier or a summary all change the card on the sheet's cast as
 * well as the tie page, and the sheet payload builds its cards server-side rather than
 * from these queries.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type {
  AdvanceTierBody,
  AllocationBody,
  AwarenessBody,
  DeclareLabelBody,
  EndLabelBody,
  ShiftLabelBody,
  SummaryBody,
  TieWriteResult,
} from './api';

export const relationshipsKeys = {
  all: ['relationships'] as const,
  /** The caller's own outbound sides — the weave wizard's partner list. */
  mine: () => [...relationshipsKeys.all, 'mine'] as const,
  tie: (relationshipId: number) => [...relationshipsKeys.all, 'tie', relationshipId] as const,
  stream: (relationshipId: number) => [...relationshipsKeys.all, 'stream', relationshipId] as const,
  types: () => [...relationshipsKeys.all, 'types'] as const,
};

/** The sheet query's key prefix (`character_sheets/queries.ts`) — a tie write moves a card on it. */
const CHARACTER_SHEETS_KEY = ['character-sheets'] as const;

/** One side of a tie. `relationshipId` null until a route param resolves. */
export function useTie(relationshipId: number | null) {
  return useQuery({
    queryKey: relationshipsKeys.tie(relationshipId ?? 0),
    queryFn: () => api.getTie(relationshipId as number),
    enabled: relationshipId != null,
    // A 404 here is the audience rule answering, not a flake: retrying it three times
    // only delays the page's not-found treatment.
    retry: false,
  });
}

/** The entries and scenes between the two sides, already filtered to this viewer. */
export function useTieStream(relationshipId: number | null) {
  return useQuery({
    queryKey: relationshipsKeys.stream(relationshipId ?? 0),
    queryFn: () => api.getTieStream(relationshipId as number),
    enabled: relationshipId != null,
    retry: false,
  });
}

/** The label catalogue, grouped by the picker. Authored content — it barely moves. */
export function useRelationshipTypes() {
  return useQuery({
    queryKey: relationshipsKeys.types(),
    queryFn: api.getRelationshipTypes,
    staleTime: 5 * 60_000,
  });
}

/** The caller's own outbound sides, OWNER-shaped. */
export function useMyTies(enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.mine(),
    queryFn: api.listMyTies,
    enabled,
  });
}

/**
 * Shared mutation shape for the seven tie writes: each invalidates the tie prefix and
 * the sheet prefix, because each moves both surfaces.
 */
function useTieWriteMutation<TBody>(mutationFn: (body: TBody) => Promise<TieWriteResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: relationshipsKeys.all }).catch(() => {});
      qc.invalidateQueries({ queryKey: CHARACTER_SHEETS_KEY }).catch(() => {});
    },
  });
}

/** Name a type on the caller's side of a tie. */
export function useDeclareLabel() {
  return useTieWriteMutation((body: DeclareLabelBody) => api.declareLabel(body));
}

/** Turn one label into another; the new row remembers what it replaced. */
export function useShiftLabel() {
  return useTieWriteMutation((body: ShiftLabelBody) => api.shiftLabel(body));
}

/** End a label. The row stays and shows as former. */
export function useEndLabel() {
  return useTieWriteMutation((body: EndLabelBody) => api.endLabel(body));
}

/** Move a label's awareness forward one stage. */
export function useAdvanceAwareness() {
  return useTieWriteMutation((body: AwarenessBody) => api.advanceAwareness(body));
}

/** Set this week's AP for the tie. */
export function useSetTieAllocation() {
  return useTieWriteMutation((body: AllocationBody) => api.setTieAllocation(body));
}

/** Claim the next tier against a capstone entry. */
export function useAdvanceTier() {
  return useTieWriteMutation((body: AdvanceTierBody) => api.advanceTier(body));
}

/** Save the summary paragraph. */
export function useSetTieSummary() {
  return useTieWriteMutation((body: SummaryBody) => api.setTieSummary(body));
}

/**
 * The other side's persona id, for the writes that name their target by persona.
 *
 * Long-lived: a character's primary persona does not move while a tie page is open.
 */
export function useTargetPersonaId(characterSheetId: number | null | undefined) {
  return useQuery({
    queryKey: [...relationshipsKeys.all, 'target-persona', characterSheetId ?? 0] as const,
    queryFn: () => api.getPersonaIdForSheet(characterSheetId as number),
    enabled: characterSheetId != null,
    staleTime: 5 * 60_000,
  });
}
