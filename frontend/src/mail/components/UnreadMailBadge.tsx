/**
 * Unread letter counter badge for the top-level navigation.
 *
 * Shows a red badge with the count of unread received mail across the
 * player's tenures. Clicking navigates to the mail inbox. Mirrors
 * `UnreadNarrativeBadge` (frontend/src/narrative/components/UnreadNarrativeBadge.tsx).
 */

import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useUnreadMailCount } from '@/mail/queries';

export function UnreadMailBadge() {
  const count = useUnreadMailCount();

  if (count === 0) return null;

  return (
    <Link
      to="/profile/mail"
      className="flex items-center gap-1.5"
      aria-label={`Letters, ${count} unread ${count === 1 ? 'letter' : 'letters'}`}
    >
      Letters
      <Badge variant="destructive" className="bg-red-600 hover:bg-red-700">
        {count}
      </Badge>
    </Link>
  );
}
