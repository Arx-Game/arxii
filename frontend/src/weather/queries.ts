/**
 * Weather React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchWeatherConditions } from './api';

/**
 * Current IC time + weather at a room. Disabled until a room is known.
 * Re-polls each minute so the IC clock (and a fresh weather roll) stays current.
 */
export function useWeatherConditions(roomId: number | null) {
  return useQuery({
    queryKey: ['weather', 'conditions', roomId],
    queryFn: () => fetchWeatherConditions(roomId as number),
    enabled: roomId != null,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
