/**
 * Locations React Query hooks (#1446).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchMyShips } from './api';

/** The requesting account's active persona's ships (owned + covenant-owned). */
export function useMyShipsQuery() {
  return useQuery({
    queryKey: ['ships', 'mine'],
    queryFn: fetchMyShips,
  });
}
