/**
 * The aura's own endpoint (#5123): reading a character's settled aura.
 *
 * The sheet payload carries the aura's shares only; who the character is (the settled
 * shares) and whether they are unsettled come from
 * `/api/magic/character-auras/`, which lists the auras of characters the caller plays.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type CharacterAura = components['schemas']['CharacterAura'];

const CHARACTER_AURAS_URL = '/api/magic/character-auras';

export const auraKeys = {
  all: ['magic', 'character-auras'] as const,
  list: (characterId: number | null) => [...auraKeys.all, 'list', characterId] as const,
};

/** GET /api/magic/character-auras/, narrowed to one character when `characterId` is given. */
export async function getCharacterAuras(characterId: number | null): Promise<CharacterAura[]> {
  const query = characterId === null ? '' : `?character=${characterId}`;
  const res = await apiFetch(`${CHARACTER_AURAS_URL}/${query}`);
  if (!res.ok) throw new Error('Failed to load the aura');
  return res.json() as Promise<CharacterAura[]>;
}

/**
 * The auras of the characters the caller plays (one, when `characterId` is given).
 * Disabled until `enabled`, so a viewer of someone else's sheet never asks.
 */
export function useCharacterAuras(characterId: number | null, enabled: boolean = true) {
  return useQuery({
    queryKey: auraKeys.list(characterId),
    queryFn: () => getCharacterAuras(characterId),
    enabled,
  });
}
