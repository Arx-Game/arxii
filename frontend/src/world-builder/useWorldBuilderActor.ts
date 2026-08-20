/**
 * useWorldBuilderActor (#3283) — the account's acting character for staff
 * builder dispatch. Ownership (IsCharacterOwner), not puppeting, is what the
 * dispatch endpoint checks, so this prefers the actively played character
 * but falls back to the account's first owned character — which makes a
 * freshly minted staff builder character usable without entering the game.
 */
import { useMemo } from 'react';

import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAppSelector } from '@/store/hooks';

export function useWorldBuilderActor(): number | null {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  return useMemo(() => {
    const active = myRosterEntries.find((entry) => entry.name === activeCharacterName);
    return active?.character_id ?? myRosterEntries[0]?.character_id ?? null;
  }, [myRosterEntries, activeCharacterName]);
}
