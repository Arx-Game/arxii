/**
 * Weather React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchWeatherConditions } from './api';

/**
 * Current IC time + weather at a room. Disabled until a room is known —
 * unless `fallbackToSelection` (the Hall's Time plate, #3539), where a null
 * room asks the server to resolve the caller's selected character's room.
 * Re-polls each minute so the IC clock (and a fresh weather roll) stays current.
 */
export function useWeatherConditions(
  roomId: number | null,
  { fallbackToSelection = false }: { fallbackToSelection?: boolean } = {}
) {
  return useQuery({
    queryKey: ['weather', 'conditions', roomId],
    queryFn: () => fetchWeatherConditions(roomId),
    enabled: roomId != null || fallbackToSelection,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
