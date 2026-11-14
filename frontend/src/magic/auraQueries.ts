/**
 * The aura's own endpoints (#5123): reading a character's settled aura and accepting
 * the changes to it.
 *
 * The sheet payload carries the aura's shares only; who the character is (the settled
 * shares), whether they are unsettled and the Mire's share come from
 * `/api/magic/character-auras/`, which lists the auras of characters the caller plays.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type { components } from '@/generated/api';

export type CharacterAura = components['schemas']['CharacterAura'];
export type AcceptAuraResponse = components['schemas']['AcceptAuraResponse'];

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

/** POST /api/magic/character-auras/{id}/accept/. A refusal is a 400 `{detail}`. */
export async function acceptAuraChanges(auraId: number): Promise<AcceptAuraResponse> {
  const res = await apiFetch(`${CHARACTER_AURAS_URL}/${auraId}/accept/`, { method: 'POST' });
  if (!res.ok) {
    await readErrorDetail(res, 'Could not accept the changes to your Aura');
  }
  return res.json() as Promise<AcceptAuraResponse>;
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

/**
 * Accept the changes to the aura. On success the aura and the character sheet refetch,
 * so the halo redraws settled.
 */
export function useAcceptAura() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ auraId }: { auraId: number; characterSheetId: number }) =>
      acceptAuraChanges(auraId),
    onSuccess: (_data, { characterSheetId }) => {
      qc.invalidateQueries({ queryKey: auraKeys.all }).catch(() => {});
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}
