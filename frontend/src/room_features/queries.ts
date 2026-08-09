/**
 * Room-features React Query hooks (#3011).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchRoomTraps } from './api';

export const roomTrapKeys = {
  forCharacter: (characterId: number) => ['room-features', 'traps', characterId] as const,
};

/**
 * Armed traps the given character can currently see in their current room
 * (#3011) — not-hidden, or already detected by that character. Disabled
 * without a character id — the room panel's `TrapsBlock` renders nothing in
 * that case (no active character puppeted).
 */
export function useRoomTrapsQuery(characterId: number | null | undefined) {
  return useQuery({
    queryKey: roomTrapKeys.forCharacter(characterId ?? 0),
    queryFn: () => fetchRoomTraps(characterId!),
    enabled: characterId != null,
    staleTime: 5_000,
  });
}
