/**
 * CrimeTab (#1765) — where your active persona is wanted, and for what.
 *
 * Self-only risk information: only rendered on the player's own sheet, and the backend
 * scopes to the viewer's active persona. Each row is one warrant — an area, the society
 * hunting you there, the pursuit tier (color-coded ladder, never a raw number), and the
 * alleged deeds behind it. Allegations render as recorded: a false accusation reads the
 * same as a true one.
 */

import { Loader2 } from 'lucide-react';

import { usePersonaHeat } from '../queries';
import type { PersonaHeatRow } from '../api';

interface Props {
  /** The viewer's active RosterEntry pk; null when no character is active. */
  viewerEntryId: number | null;
}

const TIER_STYLES: Record<string, string> = {
  watched: 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400',
  hunted: 'bg-orange-500/15 text-orange-600 dark:text-orange-400',
  heat_is_on: 'bg-red-500/15 text-red-600 dark:text-red-400',
  extreme_heat: 'bg-red-600/25 text-red-700 dark:text-red-300',
};

function TierBadge({ row }: { row: PersonaHeatRow }) {
  const style = TIER_STYLES[row.tier] ?? 'bg-muted text-muted-foreground';
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="heat-tier-badge"
    >
      {row.tier_label}
    </span>
  );
}

export function CrimeTab({ viewerEntryId }: Props) {
  const { data: rows, isLoading } = usePersonaHeat(viewerEntryId);

  if (viewerEntryId === null) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No active character to view crime records for.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="crime-empty-state">
        No one is hunting you anywhere — as far as you know.
      </p>
    );
  }

  return (
    <ul className="space-y-3" data-testid="crime-list">
      {rows.map((row) => (
        <li key={row.id} className="rounded-lg border bg-card p-4" data-testid="crime-row">
          <div className="flex items-baseline justify-between gap-3">
            <h4 className="font-medium">
              {row.area_name}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {row.society_name}
              </span>
            </h4>
            <TierBadge row={row} />
          </div>
          {row.alleged_deeds.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              Wanted for: {row.alleged_deeds.join(', ')}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
