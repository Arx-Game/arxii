/**
 * Item-facet crafting react-query hooks.
 *
 * Cache key shape:
 *   ["item-facets", itemInstanceId]  — facets attached to one item instance
 *   ["quality-tiers"]                — lookup list of quality tier records
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  craftAttachFacet,
  getCraftingQuote,
  getQualityTiers,
  listItemFacets,
  removeItemFacet,
} from '../api';

export const itemFacetKeys = {
  all: ['item-facets'] as const,
  list: (itemInstanceId: number) => ['item-facets', itemInstanceId] as const,
  qualityTiers: ['quality-tiers'] as const,
  quote: (itemInstanceId: number, facetId: number) =>
    ['crafting-quote', itemInstanceId, facetId] as const,
};

export function useItemFacets(itemInstanceId: number | undefined) {
  return useQuery({
    queryKey: itemFacetKeys.list(itemInstanceId ?? -1),
    queryFn: () => listItemFacets(itemInstanceId as number),
    enabled: itemInstanceId != null,
  });
}

export function useQualityTiers() {
  return useQuery({ queryKey: itemFacetKeys.qualityTiers, queryFn: getQualityTiers });
}

export function useCraftAttachFacet(itemInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: craftAttachFacet,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemFacetKeys.list(itemInstanceId) }).catch(() => {});
    },
  });
}

export function useCraftingQuote(itemInstanceId: number | undefined, facetId: number | undefined) {
  return useQuery({
    queryKey: itemFacetKeys.quote(itemInstanceId ?? -1, facetId ?? -1),
    queryFn: () => getCraftingQuote(itemInstanceId as number, facetId as number),
    enabled: itemInstanceId != null && facetId != null,
  });
}

export function useRemoveItemFacet(itemInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => removeItemFacet(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemFacetKeys.list(itemInstanceId) }).catch(() => {});
    },
  });
}
