/**
 * KindledResonancesPanel (#5124, demo Screen 1): "Your resonances". Each resonance the
 * character holds, with its affinity, whether a situation kindles it now, how strongly (the
 * strength's own word) and what kindled it. An unkindled one is dimmed and says so. Numbers
 * stay hidden. Mounted in the scene sidebar and in the combat rail beside Dig deep; renders
 * nothing for a character with no resonance.
 *
 * Wire contract: GET /api/magic/kindled-resonances/ (KindledResonanceViewSet).
 */

import { cn } from '@/lib/utils';
import { useKindledResonances } from '@/magic/queries';
import type { KindledResonance } from '@/magic/types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterSheetId: number;
}

/** "Kindled, blazing" when a situation kindles it (a strength word is always sent), else "Not kindled". */
function stateLabel(row: KindledResonance): string {
  return row.strength_name ? `Kindled, ${row.strength_name.toLowerCase()}` : 'Not kindled';
}

function ResonanceRow({ row }: { row: KindledResonance }) {
  return (
    <div
      className={cn(
        'space-y-0.5 rounded border border-border px-3 py-1.5',
        !row.kindled && 'opacity-60'
      )}
      data-testid={`kindled-resonance-${row.id}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span>
          <span className="text-sm font-medium">{row.name}</span>{' '}
          <span className="text-xs text-muted-foreground">{row.affinity_name}</span>
        </span>
        <span
          className={cn('text-xs', row.kindled ? 'font-medium' : 'text-muted-foreground')}
          data-testid={`kindled-resonance-state-${row.id}`}
        >
          {stateLabel(row)}
        </span>
      </div>
      {row.reasons.map((reason) => (
        <p key={reason} className="text-xs text-muted-foreground">
          {reason}
        </p>
      ))}
    </div>
  );
}

export function KindledResonancesPanel({ characterSheetId }: Props) {
  const { data: rows = [] } = useKindledResonances(characterSheetId);

  if (rows.length === 0) return null;

  return (
    <section className="space-y-1.5" data-testid="kindled-resonances-panel">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Your resonances
      </h3>
      {rows.map((row) => (
        <ResonanceRow key={row.id} row={row} />
      ))}
    </section>
  );
}
