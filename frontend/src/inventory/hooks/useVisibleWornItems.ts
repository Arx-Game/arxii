/**
 * Visible-worn-items react-query hook.
 *
 * Cache key shape:
 *   ["visible-worn", characterId]   — slim list of currently-visible worn
 *                                     items on the target character (id +
 *                                     display_name + body_region +
 *                                     equipment_layer).
 *
 * Used by ``CharacterFocusView`` when the player drills into a character
 * from the right-sidebar focus stack. The list is computed server-side
 * with the same visibility rules as the look command (concealing layers
 * hide items beneath them) — see ``visible_worn_items_for`` in
 * ``world.items.services.appearance``.
 */

import { useQuery } from '@tanstack/react-query';
import { listVisibleWornItems } from '../api';

export const visibleWornKeys = {
  all: ['visible-worn'] as const,
  list: (characterId: number) => ['visible-worn', characterId] as const,
};

export function useVisibleWornItems(characterId: number | undefined) {
  return useQuery({
    queryKey: visibleWornKeys.list(characterId ?? -1),
    queryFn: () => listVisibleWornItems(characterId as number),
    enabled: characterId != null,
    throwOnError: true,
  });
}
