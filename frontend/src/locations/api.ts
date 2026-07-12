/**
 * Locations API client (#1446) — "My Ships" reads for the Locations sheet tab.
 *
 * `GET /api/ships/ships/` is already scoped server-side (`src/world/ships/views.py`) to the
 * requesting account's active persona's owned + covenant-owned ships — no client-side
 * persona filtering needed here.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type MyShip = components['schemas']['ShipDetails'];

interface PaginatedShips {
  results: MyShip[];
}

/** Fetch the requesting account's active persona's ships (owned + covenant-owned). */
export async function fetchMyShips(): Promise<MyShip[]> {
  const res = await apiFetch('/api/ships/ships/');
  if (!res.ok) throw new Error('Failed to load ships');
  const data = (await res.json()) as PaginatedShips | MyShip[];
  return Array.isArray(data) ? data : data.results;
}

export type PortalDestination = components['schemas']['PortalDestination'];

interface PaginatedPortalDestinations {
  results: PortalDestination[];
}

/**
 * Fetch every anchor the given character could portal-travel to right now
 * (#2222 Task 5). Rides `GET /api/locations/portal-destinations/?character_id=`
 * (Task 4), which already applies the full leak-safe visibility contract
 * server-side — this client does no filtering of its own. Paginated
 * (page_size 50); the room-sidebar list is expected to be small, so this
 * reads only the first page.
 */
export async function fetchPortalDestinations(characterId: number): Promise<PortalDestination[]> {
  const res = await apiFetch(`/api/locations/portal-destinations/?character_id=${characterId}`);
  if (!res.ok) throw new Error('Failed to load portal destinations');
  const data = (await res.json()) as PaginatedPortalDestinations;
  return data.results;
}
