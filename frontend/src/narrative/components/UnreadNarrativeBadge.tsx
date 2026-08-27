/**
 * Unread narrative message counter badge for the top-level navigation.
 *
 * Shows a red badge with the count of unacknowledged narrative messages
 * (account-wide — `MyNarrativeMessagesView` scopes to every character the
 * account owns, not just one puppet; see `narrative/CLAUDE.md`).
 *
 * Routing (#3412 hygiene fold-in): now that `gameSlice.active` is a durable,
 * hydration-safe selection, clicking routes to the SELECTED character's
 * sheet — previously this always linked to `myEntries[0]`, so switching to
 * an alt via the docked chip left the badge pointing at the wrong sheet.
 * With no selection, falls back to the roster (an "account fallback": there
 * is no single character to deep-link to, so the count stays a grouped
 * account-wide total and the click just sends the player to pick one).
 * `#messages` was dropped (dead fragment) — the SPA never scrolled to it
 * (no hash-scroll handling), so it was inert.
 */

import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useUnreadNarrativeCount } from '@/narrative/queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAppSelector } from '@/store/hooks';

export function UnreadNarrativeBadge() {
  const count = useUnreadNarrativeCount();
  const { data: myEntries } = useMyRosterEntriesQuery();
  const activeCharacterName = useAppSelector((state) => state.game.active);

  if (count === 0) return null;

  const activeEntry = myEntries?.find((entry) => entry.name === activeCharacterName);
  const targetCharacterId = activeEntry?.id ?? myEntries?.[0]?.id;
  const to = targetCharacterId ? `/characters/${targetCharacterId}` : '/roster';

  return (
    <Link to={to} aria-label={`${count} unread narrative ${count === 1 ? 'message' : 'messages'}`}>
      <Badge variant="destructive" className="bg-red-600 hover:bg-red-700">
        {count}
      </Badge>
    </Link>
  );
}
