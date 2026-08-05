/**
 * Visible-markings react-query hook (#2985).
 *
 * Cache key shape:
 *   ["visible-markings", characterId, observerId]
 *     — the body markings (tattoos, scars, brands) on ``characterId``
 *     visible to ``observerId``, computed server-side with the same
 *     coverage/reveal/disguise rules as the look command — see
 *     ``visible_markings_for`` in ``world.forms.services.markings``.
 *
 * Mirrors ``useVisibleWornItems``: observer required for non-staff, hook
 * disabled until both ids are available.
 */

import { useQuery } from '@tanstack/react-query';
import { listVisibleMarkings } from '../api';

export const visibleMarkingKeys = {
  all: ['visible-markings'] as const,
  list: (characterId: number, observerId: number) =>
    ['visible-markings', characterId, observerId] as const,
};

export function useVisibleMarkings(
  characterId: number | undefined,
  observerId: number | undefined
) {
  return useQuery({
    queryKey: visibleMarkingKeys.list(characterId ?? -1, observerId ?? -1),
    queryFn: () => listVisibleMarkings(characterId as number, observerId as number),
    enabled: characterId != null && observerId != null,
    throwOnError: true,
  });
}
