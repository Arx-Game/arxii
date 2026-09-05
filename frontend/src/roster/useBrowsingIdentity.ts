/**
 * This browser tab's browsing identity (#3479) — the `RosterEntry` ambient,
 * non-game pages should treat as "who am I browsing as," independent of
 * whichever character this tab's own `/game` surface happens to have
 * focused. `gameSlice.active`/`activeEntryId` stay reserved for live-session
 * concerns (in-tab session focus, `GatefoldPage`'s ADR-0247 redirect) — see
 * the #3479 ledger's consumer table for the full split. Ambient pages (the
 * Hall, Tidings, Wardrobe, Magic, the character sheet, Market, Orgs, Goals,
 * Fashion, the Story Builder, the world-builder/GM-adjudication actor
 * resolvers, the unread-narrative badge, the Treat panel) read this hook
 * instead of `useAppSelector((state) => state.game.active)`.
 *
 * Backed by `gameSlice.browsingEntryId` (mirrored from
 * `store/browsingIdentity.ts`'s per-tab `sessionStorage` store by
 * `useAccountQuery`'s hydration effect, see `evennia_replacements/queries.tsx`)
 * plus `useMyRosterEntriesQuery` to resolve the id to a name/full entry —
 * the same roster-entries query almost every one of these pages already
 * called to resolve `active` (a NAME) to an id; the id is now the source of
 * truth, and this hook resolves the lookup in the other direction.
 */
import { useAppSelector } from '@/store/hooks';
import { selectBrowsingEntryId } from '@/store/gameSlice';
import { useMyRosterEntriesQuery } from './queries';
import type { MyRosterEntry } from './types';

export interface BrowsingIdentity {
  /** This tab's browsing `RosterEntry.id`, or null before hydration / with no selection. */
  entryId: number | null;
  /** The resolved entry's name, or null when `entryId` is null or not (yet) in the roster query. */
  name: string | null;
  /** The full roster entry, or null under the same conditions as `name`. */
  entry: MyRosterEntry | null;
}

export function useBrowsingIdentity(): BrowsingIdentity {
  const entryId = useAppSelector(selectBrowsingEntryId);
  const { data: myEntries } = useMyRosterEntriesQuery();
  const entry = entryId != null ? (myEntries?.find((e) => e.id === entryId) ?? null) : null;
  return { entryId, name: entry?.name ?? null, entry };
}
