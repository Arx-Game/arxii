/**
 * PendingAlterationBanner — site-wide alert when the account has an OPEN
 * PendingAlteration (#877). The scar gates XP spending, so it must be
 * impossible to miss; this is the notification surface (no header badge).
 * Renders nothing while logged out, loading, or clean.
 */

import { Link } from 'react-router-dom';
import { usePendingAlterations } from '../../queries';

export function PendingAlterationBanner() {
  const { data } = usePendingAlterations();
  const pendings = data?.results ?? [];
  if (pendings.length === 0) return null;

  const [first] = pendings;
  const message =
    pendings.length === 1
      ? `Your magic has marked you — ${first.character_name} carries an unresolved ` +
        `${first.tier_display} Mage Scar. That character's XP spending is blocked until it is faced.`
      : `Your magic has marked you — ${pendings.length} unresolved Mage Scars are blocking ` +
        `XP spending.`;
  const linkText = pendings.length === 1 ? 'Resolve it' : 'Resolve them';

  return (
    <div
      data-testid="pending-alteration-banner"
      role="alert"
      className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-center text-sm text-destructive"
    >
      <span>{message}</span>{' '}
      <Link to="/magic/alterations" className="font-semibold underline underline-offset-2">
        {linkText}
      </Link>
    </div>
  );
}
