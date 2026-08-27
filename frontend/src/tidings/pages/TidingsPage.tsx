/** The Tidings page (#1450) — the public-reaction center's browse/pull view.
 *
 * Public awareness scopes to the ACTIVE character (never the account), so we resolve the active
 * character's roster entry from the game state, exactly as the character sheet's IC tabs do. */
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAuthStatus } from '@/evennia_replacements/queries';

import { TidingsFeed } from '../components/TidingsFeed';

export function TidingsPage() {
  // This route is NOT behind ProtectedRoute (Tidings is public), so a hard
  // reload lands here before `useAccountQuery`'s hydration effect has had a
  // chance to mirror the durable selection into `gameSlice.active` (#3412
  // review fix). `authLoading` covers that window; once the account
  // resolves with a real selection, `entriesLoading` covers the shorter gap
  // until the roster query catches up enough to resolve the id.
  const { data: myEntries, isLoading: entriesLoading } = useMyRosterEntriesQuery();
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { isLoading: authLoading } = useAuthStatus();
  const isResolvingViewer = authLoading || (activeCharacterName != null && entriesLoading);
  const viewerEntryId = myEntries?.find((e) => e.name === activeCharacterName)?.id ?? null;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <div>
        <h1 className="text-2xl font-semibold">Tidings</h1>
        <p className="text-muted-foreground">
          The deeds your circles celebrate and the scandals they whisper about.
        </p>
      </div>
      <TidingsFeed viewerId={viewerEntryId} isResolvingViewer={isResolvingViewer} />
    </div>
  );
}
