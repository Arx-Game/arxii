/**
 * Weather React Query hooks (#1522).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchWeatherConditions } from './api';

/**
 * Current IC time + weather at a room. Disabled until a room is known —
 * unless `fallbackToSelection` (the Hall's Time plate, #3539), where a null
 * room asks the server to resolve the acting character's room; `entryId`
 * (the tab's browsing identity, #3479) names which character that is, and
 * null falls back to the account's durable selection. It only matters on the
 * no-room path: the server ignores it when `room_id` is sent, which is why
 * the in-game WeatherWidget (always room-keyed to this tab's live session)
 * doesn't pass it.
 * Re-polls each minute so the IC clock (and a fresh weather roll) stays current.
 */
export function useWeatherConditions(
  roomId: number | null,
  {
    fallbackToSelection = false,
    entryId = null,
  }: { fallbackToSelection?: boolean; entryId?: number | null } = {}
) {
  return useQuery({
    queryKey: ['weather', 'conditions', roomId, { entryId }],
    queryFn: () => fetchWeatherConditions(roomId, entryId),
    enabled: roomId != null || fallbackToSelection,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
