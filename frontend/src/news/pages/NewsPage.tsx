/** The News & Gossip page (#1450) — the public-reaction center's browse/pull view.
 *
 * Public awareness scopes to the ACTIVE character (never the account), so we resolve the active
 * character's roster entry from the game state, exactly as the character sheet's IC tabs do. */
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';

import { NewsFeed } from '../components/NewsFeed';

export function NewsPage() {
  const { data: myEntries } = useMyRosterEntriesQuery();
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const viewerEntryId = myEntries?.find((e) => e.name === activeCharacterName)?.id ?? null;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <div>
        <h1 className="text-2xl font-semibold">News &amp; Gossip</h1>
        <p className="text-muted-foreground">
          The deeds your circles celebrate and the scandals they whisper about.
        </p>
      </div>
      <NewsFeed viewerId={viewerEntryId} />
    </div>
  );
}
