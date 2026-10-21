/**
 * Keepsake react-query hooks (#4530).
 *
 * Cache key shape:
 *   ["keepsake", itemId]  — the item panel's keepsake form data for one held item
 *
 * Declaring and releasing dispatch the registry actions as the character; both refresh the
 * form data and the inventory, since examine's credits can carry the keeper's words.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  declareKeepsake,
  getKeepsakeState,
  releaseKeepsake,
  type DeclareKeepsakePayload,
} from '../api';

export const keepsakeKeys = {
  item: (itemId: number) => ['keepsake', itemId] as const,
};

export function useKeepsakeState(itemId: number | undefined, enabled = true) {
  return useQuery({
    queryKey: keepsakeKeys.item(itemId ?? -1),
    queryFn: () => getKeepsakeState(itemId as number),
    enabled: enabled && itemId != null,
  });
}

function useKeepsakeMutation<T>(mutationFn: (variables: T) => ReturnType<typeof declareKeepsake>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['keepsake'] }).catch(() => {});
      qc.invalidateQueries({ queryKey: ['inventory'] }).catch(() => {});
    },
  });
}

export function useDeclareKeepsake(characterId: number) {
  return useKeepsakeMutation((payload: DeclareKeepsakePayload) =>
    declareKeepsake(characterId, payload)
  );
}

export function useReleaseKeepsake(characterId: number) {
  return useKeepsakeMutation((itemId: number) => releaseKeepsake(characterId, itemId));
}
