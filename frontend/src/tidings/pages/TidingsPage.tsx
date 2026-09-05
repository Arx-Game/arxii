/** The Tidings page (#1450) — the public-reaction center's browse/pull view.
 *
 * Public awareness scopes to the ACTIVE character (never the account), so we resolve this
 * tab's browsing identity (#3479), exactly as the character sheet's IC tabs do. */
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { useAuthStatus } from '@/evennia_replacements/queries';

import { TidingsFeed } from '../components/TidingsFeed';

export function TidingsPage() {
  // This route is NOT behind ProtectedRoute (Tidings is public), so a hard
  // reload lands here before `useAccountQuery`'s hydration effect has had a
  // chance to mirror the durable selection into this tab's browsing identity
  // (#3479 — the id comes straight off `gameSlice.browsingEntryId`, no
  // separate roster-query resolution step needed). `authLoading` covers that
  // hydration window.
  const { entryId: viewerEntryId } = useBrowsingIdentity();
  const { isLoading: authLoading } = useAuthStatus();

  return (
    <div className="container mx-auto space-y-4 p-4">
      <div>
        <h1 className="text-2xl font-semibold">Tidings</h1>
        <p className="text-muted-foreground">
          The deeds your circles celebrate and the scandals they whisper about.
        </p>
      </div>
      <TidingsFeed viewerId={viewerEntryId} isResolvingViewer={authLoading} />
    </div>
  );
}
