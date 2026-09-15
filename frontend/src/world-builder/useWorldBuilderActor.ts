/**
 * useWorldBuilderActor (#3283) — the account's acting character for staff
 * builder dispatch. Ownership (IsCharacterOwner), not puppeting, is what the
 * dispatch endpoint checks, so this prefers this tab's browsing identity
 * (#3479) but falls back to the account's first owned character, which
 * makes a freshly minted staff builder character usable without entering
 * the game.
 */
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';

export function useWorldBuilderActor(): number | null {
  const { entry } = useBrowsingIdentity();
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  return entry?.character_id ?? myRosterEntries[0]?.character_id ?? null;
}
