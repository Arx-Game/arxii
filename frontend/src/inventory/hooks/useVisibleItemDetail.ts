/**
 * Visible-item-detail react-query hook.
 *
 * Cache key shape:
 *   ["visible-item-detail", itemId, observerId]
 *     — full ItemInstanceRead shape for a single item the requester's
 *     ``observerId`` (one of their own characters) is allowed to
 *     inspect: same room as the wearing character (concealment rules
 *     apply), self-look (bypass concealment), or staff (bypass).
 *
 * Used by ``ItemFocusView`` to render the read-only sidebar drill-in for
 * "looking at" someone else's worn item. The observer parameter is
 * required for non-staff; the backend returns 404 when the requester
 * cannot view the item, so an "unavailable" state is rendered.
 */

import { useQuery } from '@tanstack/react-query';
import { getVisibleItemDetail } from '../api';

export const visibleItemDetailKeys = {
  all: ['visible-item-detail'] as const,
  detail: (itemId: number, observerId: number) =>
    ['visible-item-detail', itemId, observerId] as const,
};

export function useVisibleItemDetail(itemId: number | undefined, observerId: number | undefined) {
  return useQuery({
    queryKey: visibleItemDetailKeys.detail(itemId ?? -1, observerId ?? -1),
    queryFn: () => getVisibleItemDetail(itemId as number, observerId as number),
    enabled: itemId != null && observerId != null,
    throwOnError: true,
  });
}
