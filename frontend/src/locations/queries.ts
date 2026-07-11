/**
 * Locations React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchMyShips, fetchPortalDestinations } from './api';

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

/**
 * Anchors the given character could portal-travel to right now (#2222 Task 5).
 * Disabled without a character id — the room panel's `PortalsBlock` renders
 * nothing in that case (no active character puppeted).
 */
export function usePortalDestinationsQuery(characterId: number | null | undefined) {
  return useQuery({
    queryKey: ['locations', 'portal-destinations', characterId ?? 0],
    queryFn: () => fetchPortalDestinations(characterId!),
    enabled: characterId != null,
    staleTime: 15_000,
  });
}
