import { useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import type { MyRosterEntry } from './types';
import { useMyRosterEntriesQuery } from './queries';

/**
 * The persona id a character is ACTING as right now — the worn face (#981).
 *
 * `active_persona_id` is serialized with the primary fallback already applied
 * server-side (`RosterEntrySerializer.get_active_persona_id`), so it is the
 * single source of truth for "which face is this character presenting"; the
 * extra `primary_persona_id` fallback here only covers stale cached payloads.
 *
 * Use this — never `primary_persona_id` directly — anywhere the id feeds an
 * IC-meaningful write (pose/action initiator) or self-matching read
 * (attention routing, own-pose exclusion). Reading the primary while a mask
 * or ESTABLISHED alt is worn both unmasks the disguise on writes and breaks
 * self-matching on reads, since the server broadcasts the worn face.
 */
export function actingPersonaId(
  entry: Pick<MyRosterEntry, 'active_persona_id' | 'primary_persona_id'> | null | undefined
): number | null {
  return entry?.active_persona_id ?? entry?.primary_persona_id ?? null;
}

/**
 * The viewer's own active persona id right now (#3787) -- extracted from
 * `PoseUnit.tsx`'s self-pose guard (`activeCharacterName` +
 * `useMyRosterEntriesQuery` + `actingPersonaId`) so a second call site (the
 * involvement mark in `ThreadedNarrativeReader.tsx`) reuses the exact same
 * resolution instead of re-deriving "who am I" in parallel. `PoseUnit` itself
 * now calls this hook rather than computing the same three lines inline.
 */
export function useViewerPersonaId(): number | null {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  return useMemo(
    () => actingPersonaId(myRosterEntries.find((e) => e.name === activeCharacterName)),
    [myRosterEntries, activeCharacterName]
  );
}
