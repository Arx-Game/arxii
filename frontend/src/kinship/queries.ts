/** React Query hooks for the kin tree + pairwise relationship reads (#2062, #3003). */
import { useQuery } from '@tanstack/react-query';

import { getFamilySlots } from '@/character-creation/api';
import { getFamilyTree, getKinRelationship, getKinTree } from './api';

export const kinshipKeys = {
  tree: (characterId: number) => ['kinship', 'tree', characterId] as const,
  family: (familyId: number) => ['kinship', 'family', familyId] as const,
  familySlots: (familyId: number) => ['kinship', 'family-slots', familyId] as const,
  relationship: (a: number, b: number) => ['kinship', 'relationship', a, b] as const,
};

/** The kin tree centred on `characterId` (a CharacterSheet pk). */
export function useKinTree(characterId: number) {
  return useQuery({
    queryKey: kinshipKeys.tree(characterId),
    queryFn: () => getKinTree(characterId),
  });
}

/** The family page's tree, keyed by a Family pk (#4209). */
export function useFamilyTree(familyId: number | undefined) {
  return useQuery({
    queryKey: kinshipKeys.family(familyId ?? -1),
    queryFn: () => getFamilyTree(familyId as number),
    enabled: familyId != null,
  });
}

/**
 * The family's open seats (#4209): the CG slot browser's own payload. A family
 * CG cannot pick answers with none, so the section simply vanishes.
 */
export function useFamilySlots(familyId: number | undefined) {
  return useQuery({
    queryKey: kinshipKeys.familySlots(familyId ?? -1),
    queryFn: () => getFamilySlots(familyId as number),
    enabled: familyId != null,
  });
}

/**
 * The derived relationship label between two CharacterSheet pks.
 *
 * `b` is nullable/undefined on purpose: a selected kin-tree node's `id` is a
 * Kinsperson pk, not a CharacterSheet pk (see `KinspersonNode.sheet_id` in
 * `types.ts`) — most kin are unplayed NPCs with no bound sheet at all, so the
 * query is disabled until a real CharacterSheet pk is known for the selection.
 */
export function useKinRelationship(a: number, b: number | null | undefined) {
  return useQuery({
    queryKey: kinshipKeys.relationship(a, b ?? -1),
    queryFn: () => getKinRelationship(a, b as number),
    enabled: b != null,
  });
}
