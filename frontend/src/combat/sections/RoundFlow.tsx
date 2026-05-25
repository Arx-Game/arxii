/**
 * RoundFlow — rail section showing round status, declarations count,
 * and per-participant initiative chips.
 *
 * Data sources: EncounterDetail
 * - round_number
 * - participants[]
 * - current_round_actions[] — participants with an action entry have acted
 *
 * Initiative chip states:
 * - Acted (✓): participant has a row in current_round_actions
 * - Pending (…): participant has no row in current_round_actions
 *
 * NOTE: "Current" (currently acting) state is not derivable from EncounterDetail
 * alone — it would require a richer server-side indicator. For Phase 8, chips
 * show "acted" vs "pending" only. Current-acting state can be added when the
 * server exposes it.
 * TODO(round-flow): add "current" chip state when backend exposes active actor.
 *
 * Phase 8, Task 8.5 — unified-combat-ui plan.
 */

import { cn } from '@/lib/utils';
import type { EncounterDetail, Participant, RoundAction } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RoundFlowProps {
  encounter: EncounterDetail;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a set of participant IDs that have acted this round.
 *
 * current_round_actions has shape {[key: string]: unknown}[]. The backend's
 * RoundActionSerializer includes `participant` (the CombatParticipant PK).
 * We read it safely with a type guard.
 */
function buildActedSet(roundActions: RoundAction[]): Set<number> {
  const acted = new Set<number>();
  for (const action of roundActions) {
    const pid = action['participant'];
    if (typeof pid === 'number') {
      acted.add(pid);
    }
  }
  return acted;
}

// ---------------------------------------------------------------------------
// InitiativeChip — one participant's acted/pending indicator
// ---------------------------------------------------------------------------

interface ChipProps {
  participant: Participant;
  hasActed: boolean;
}

function InitiativeChip({ participant, hasActed }: ChipProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-medium',
        hasActed
          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
          : 'border-border bg-muted text-muted-foreground'
      )}
      data-testid={`initiative-chip-${participant.id}`}
      title={hasActed ? 'Acted this round' : 'Pending'}
    >
      <span className="shrink-0">{hasActed ? '✓' : '…'}</span>
      <span className="max-w-[80px] truncate">{participant.character_name}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoundFlow
// ---------------------------------------------------------------------------

export function RoundFlow({ encounter, collapsed = false, onToggleCollapse }: RoundFlowProps) {
  const {
    round_number: roundNumber,
    participants,
    current_round_actions: roundActions,
  } = encounter;

  const actedSet = buildActedSet(roundActions);
  const actedCount = participants.filter((p) => actedSet.has(p.id)).length;
  const totalCount = participants.length;

  return (
    <div className="rounded-md border border-border bg-card" data-testid="round-flow-section">
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="round-flow-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Round Flow
        </span>
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed ? '-rotate-90' : 'rotate-0'
          )}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="space-y-3 border-t border-border px-3 py-2">
          {/* Round summary line */}
          <p className="text-xs text-muted-foreground" data-testid="round-flow-summary">
            Round {roundNumber ?? 0} &middot; {actedCount}/{totalCount} acted
          </p>

          {/* Declarations counter */}
          <div
            className="flex items-center justify-between rounded border border-border bg-muted/30 px-2 py-1"
            data-testid="declarations-counter"
          >
            <span className="text-xs text-muted-foreground">Declarations ready</span>
            <span className="font-mono text-xs font-semibold text-foreground">
              {actedCount} / {totalCount}
            </span>
          </div>

          {/* Initiative order chips */}
          {participants.length > 0 && (
            <div className="flex flex-wrap gap-1.5" data-testid="initiative-chips">
              {participants.map((p) => (
                <InitiativeChip key={p.id} participant={p} hasActed={actedSet.has(p.id)} />
              ))}
            </div>
          )}

          {participants.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="round-flow-empty">
              No participants yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
