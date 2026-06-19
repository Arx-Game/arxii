import { useMutation, useQueryClient } from '@tanstack/react-query';
import { postUseItem } from '../api';
import { inventoryKeys } from './useInventory';

export function useUseItem(characterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: number) => postUseItem(itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: inventoryKeys.inventory(characterId) }).catch(() => {});
    },
  });
}
