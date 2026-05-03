/**
 * Visible-item-detail react-query hook.
 *
 * Cache key shape:
 *   ["visible-item-detail", itemId]   — full ItemInstanceRead shape for a
 *                                       single item the requester is
 *                                       allowed to inspect (own items, or
 *                                       items currently visibly worn on a
 *                                       character sharing one of their
 *                                       rooms; staff bypass).
 *
 * Used by ``ItemFocusView`` to render the read-only sidebar drill-in for
 * "looking at" someone else's worn item.
 */

import { useQuery } from '@tanstack/react-query';
import { getVisibleItemDetail } from '../api';

export const visibleItemDetailKeys = {
  all: ['visible-item-detail'] as const,
  detail: (itemId: number) => ['visible-item-detail', itemId] as const,
};

export function useVisibleItemDetail(itemId: number | undefined) {
  return useQuery({
    queryKey: visibleItemDetailKeys.detail(itemId ?? -1),
    queryFn: () => getVisibleItemDetail(itemId as number),
    enabled: itemId != null,
    throwOnError: true,
  });
}
