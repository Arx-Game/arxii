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
