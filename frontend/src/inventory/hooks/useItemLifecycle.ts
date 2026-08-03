/**
 * Item lifecycle mutations (#2886): accent removal + recycling.
 *
 * Both are irreversible — callers confirm via AlertDialog before firing.
 * Invalidate the whole inventory key family: removal changes the item's
 * serialized accents; recycling removes the item and may add salvage rows.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { postRecycleItem, postRemoveAccent, postRequestRecycleApproval } from '../api';

export function useRemoveAccent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, accentTarget }: { itemId: number; accentTarget: number }) =>
      postRemoveAccent(itemId, accentTarget),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory'] }).catch(() => {});
    },
  });
}

export function useRecycleItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => postRecycleItem(itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory'] }).catch(() => {});
    },
  });
}

export function useRequestRecycleApproval() {
  return useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => postRequestRecycleApproval(itemId),
  });
}
