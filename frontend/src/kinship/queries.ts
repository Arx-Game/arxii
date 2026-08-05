/** React Query hooks for the kin tree + pairwise relationship reads (#2062, #3003). */
import { useQuery } from '@tanstack/react-query';

import { getKinRelationship, getKinTree } from './api';

export const kinshipKeys = {
  tree: (characterId: number) => ['kinship', 'tree', characterId] as const,
  relationship: (a: number, b: number) => ['kinship', 'relationship', a, b] as const,
};

/** The kin tree centred on `characterId` (a CharacterSheet pk). */
export function useKinTree(characterId: number) {
  return useQuery({
    queryKey: kinshipKeys.tree(characterId),
    queryFn: () => getKinTree(characterId),
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
