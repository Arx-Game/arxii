import { useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { reactToInteraction } from '../queries';

// Matches ReactionWindowKind.KUDOS's wire value (src/world/scenes/constants.py).
export const KUDOS_KIND = 'kudos';

/**
 * The first kudos on a pose (#2031): lazily opens the pose's kudos window
 * and records the viewer's reaction in one call. It was the standalone chip
 * under every card; since #4128 the play menu on the avatar offers it, so the
 * strip and the menu share this one hook.
 */
export function useKudos(sceneId: string, interactionId: number) {
  const queryClient = useQueryClient();
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const personaId = useMemo(
    () => actingPersonaId(myRosterEntries.find((e) => e.name === activeCharacterName)),
    [myRosterEntries, activeCharacterName]
  );
  const mutation = useMutation({
    mutationFn: () =>
      reactToInteraction({
        persona_id: personaId as number,
        interaction_id: interactionId,
        kind: KUDOS_KIND,
        choice: KUDOS_KIND,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
  return {
    personaId,
    give: () => mutation.mutate(),
    canGive: personaId != null && !mutation.isPending,
    isPending: mutation.isPending,
    error: mutation.error,
  };
}
