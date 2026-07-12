/**
 * Item-creation crafting react-query hooks (#2240).
 *
 * Cache key shape:
 *   ["craftable-recipes"]          — recipes this character can mint
 *   ["create-item-quote", tplId]   — cost/quality quote for one template
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  craftCreateItem,
  getCreateItemQuote,
  listCraftableRecipes,
} from '../api';

export const itemCreationKeys = {
  recipes: ['craftable-recipes'] as const,
  quote: (templateId: number) => ['create-item-quote', templateId] as const,
};

export function useCraftableRecipes() {
  return useQuery({ queryKey: itemCreationKeys.recipes, queryFn: listCraftableRecipes });
}

export function useCreateItemQuote(templateId: number | undefined) {
  return useQuery({
    queryKey: itemCreationKeys.quote(templateId ?? -1),
    queryFn: () => getCreateItemQuote(templateId as number),
    enabled: templateId != null,
  });
}

export function useCraftCreateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: craftCreateItem,
    onSuccess: () => {
      // A new item lands in inventory — refresh the caller's inventory views.
      qc.invalidateQueries({ queryKey: ['inventory'] }).catch(() => {});
    },
  });
}
