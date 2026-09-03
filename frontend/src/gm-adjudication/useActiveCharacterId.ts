/**
 * The roster character the viewer is acting as, or null (#3564).
 *
 * Moved out of `GMAdjudicationPanel` so the beat form can dispatch GM
 * actions too (see `GMAdjudicationPanel.tsx`, which now calls this hook
 * instead of duplicating the resolution).
 */

import { useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';

export function useActiveCharacterId(): number | null {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  return useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
}
