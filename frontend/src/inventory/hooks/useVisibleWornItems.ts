/**
 * Visible-worn-items react-query hook.
 *
 * Cache key shape:
 *   ["visible-worn", characterId, observerId]
 *     — slim list of currently-visible worn items on ``characterId`` as
 *     seen by ``observerId`` (one of the requester's own characters).
 *
 * Used by ``CharacterFocusView`` when the player drills into a character
 * from the right-sidebar focus stack. The list is computed server-side
 * with the same visibility rules as the look command (concealing layers
 * hide items beneath them) — see ``visible_worn_items_for`` in
 * ``world.items.services.appearance``.
 *
 * The observer parameter is required for non-staff requests; the
 * backend enforces same-room / self-look permissions. The hook is
 * disabled until both ids are available.
 */

import { useQuery } from '@tanstack/react-query';
import { listVisibleWornItems } from '../api';

export const visibleWornKeys = {
  all: ['visible-worn'] as const,
  list: (characterId: number, observerId: number) =>
    ['visible-worn', characterId, observerId] as const,
};

export function useVisibleWornItems(
  characterId: number | undefined,
  observerId: number | undefined
) {
  return useQuery({
    queryKey: visibleWornKeys.list(characterId ?? -1, observerId ?? -1),
    queryFn: () => listVisibleWornItems(characterId as number, observerId as number),
    enabled: characterId != null && observerId != null,
    throwOnError: true,
  });
}
