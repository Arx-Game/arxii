/**
 * When a lent NPC's loan ends (take-back, scene finish, decline), its entry drops out of
 * the account's `mine` list. A tab that was playing it must not keep the NPC as its
 * speaker: it falls back to the account's own remaining character, a PC before an NPC
 * (#4418). The list is refetched on focus and on an interval; the server pushes nothing
 * for loan changes.
 */
import { useEffect, useRef } from 'react';

import type { MyRosterEntry } from '@/roster/types';
import { useSelectCharacterMutation } from '@/roster/queries';
import { writeTabIdentity } from '@/store/browsingIdentity';
import { hydrateActiveCharacter, setActiveSession, setBrowsingIdentity } from '@/store/gameSlice';
import { useAppDispatch } from '@/store/hooks';

/** A PC if the account has one, else any remaining character. */
export function fallbackEntry(characters: MyRosterEntry[]): MyRosterEntry | null {
  return characters.find((c) => c.roster_type !== 'NPC') ?? characters[0] ?? null;
}

export function useLoanEndFallback(
  characters: MyRosterEntry[],
  active: string | null,
  hasSession: (name: string) => boolean
): void {
  const dispatch = useAppDispatch();
  const { mutate: selectCharacter } = useSelectCharacterMutation();
  // The last listed character this tab was on, kept past an account refetch that clears `active`.
  const lastActive = useRef<string | null>(null);

  useEffect(() => {
    // Only a character seen in the list counts: a name that never was there did not leave it.
    if (active && characters.some((c) => c.name === active)) lastActive.current = active;
    const previous = lastActive.current;
    if (!previous || characters.length === 0) return;
    if (characters.some((c) => c.name === previous)) return;
    const next = fallbackEntry(characters);
    if (!next) return;
    lastActive.current = next.name;
    writeTabIdentity(next.id);
    dispatch(setBrowsingIdentity(next.id));
    if (hasSession(next.name)) {
      dispatch(setActiveSession(next.name));
    } else {
      dispatch(hydrateActiveCharacter({ name: next.name, entryId: next.id }));
    }
    selectCharacter(next.id);
  }, [characters, active, dispatch, hasSession, selectCharacter]);
}
