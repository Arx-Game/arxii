/**
 * Locations React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchMyShips } from './api';

/**
 * The requesting account's active persona's ships (owned + covenant-owned).
 *
 * `GET /api/ships/ships/` is server-scoped to the account's ACTIVE persona, so callers
 * viewing a non-active character's sheet must pass `enabled: false` — otherwise this
 * would silently fetch and render the wrong character's ships (#1446 final review).
 */
export function useMyShipsQuery(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['ships', 'mine'],
    queryFn: fetchMyShips,
    enabled: options.enabled ?? true,
  });
}
