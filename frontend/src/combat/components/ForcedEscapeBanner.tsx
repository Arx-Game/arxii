/**
 * ForcedEscapeBanner — "you must run" stakes banner (#875).
 *
 * Rendered by CombatTurnPanel for a live encounter whose `forced_escape` flag
 * is set: an unbeatable Hero Killer is on the field, so victory is impossible
 * and the party must flee.
 */

import { cn } from '@/lib/utils';

export function ForcedEscapeBanner() {
  return (
    <div
      role="alert"
      className={cn(
        'rounded-md border px-4 py-3 text-center text-lg font-semibold tracking-wide',
        'border-red-600/70 bg-red-950/50 text-red-200 animate-pulse'
      )}
    >
      You cannot win this fight — you must run.
    </div>
  );
}
