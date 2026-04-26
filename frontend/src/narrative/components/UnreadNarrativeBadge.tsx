/**
 * Unread narrative message counter badge for the top-level navigation.
 *
 * Shows a red badge with the count of unacknowledged narrative messages.
 * Clicking navigates to the messages section of the character sheet.
 *
 * Phase 4 scope: links to the first (puppeted) character only.
 * Multi-character handling can be refined in Phase 5.
 */

import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useUnreadNarrativeCount } from '@/narrative/queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';

export function UnreadNarrativeBadge() {
  const count = useUnreadNarrativeCount();
  const { data: myEntries } = useMyRosterEntriesQuery();

  if (count === 0) return null;

  // Link to the first character's messages section.
  const primaryCharacterId = myEntries?.[0]?.id;
  const to = primaryCharacterId ? `/characters/${primaryCharacterId}#messages` : '/roster';

  return (
    <Link to={to} aria-label={`${count} unread narrative ${count === 1 ? 'message' : 'messages'}`}>
      <Badge variant="destructive" className="bg-red-600 hover:bg-red-700">
        {count}
      </Badge>
    </Link>
  );
}
