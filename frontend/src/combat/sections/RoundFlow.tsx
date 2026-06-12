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
 * GM end-encounter control (#876): when the viewer is the scene GM and the
 * encounter is still live, an "End Encounter" button (AlertDialog-confirmed)
 * calls POST /api/combat/{id}/end/ via useEndEncounter.
 */

import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { useEndEncounter } from '../queries';
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
// EscalationStrip — pressure level + tick narration for escalating encounters
// ---------------------------------------------------------------------------

const ROMAN = ['0', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

/** Highest escalation level among participants (encounter-wide ramp). */
function escalationLevel(participants: Participant[]): number {
  return Math.max(0, ...participants.map((p) => p.escalation_level ?? 0));
}

function EscalationStrip({ encounter }: { encounter: EncounterDetail }) {
  if (!encounter.escalation_curve_name) {
    return null;
  }
  const level = escalationLevel(encounter.participants);
  return (
    <div
      className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1.5"
      data-testid="escalation-strip"
    >
      <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-300">
        Escalation {ROMAN[Math.min(level, ROMAN.length - 1)]}
      </span>
      {encounter.escalation_tick_narration && (
        <p className="mt-0.5 text-xs italic text-muted-foreground">
          {encounter.escalation_tick_narration}
        </p>
      )}
    </div>
  );
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

  // GM end-encounter control (#876).
  const endEncounter = useEndEncounter(encounter.id);
  const showEndControl = encounter.is_gm && encounter.status !== 'completed';

  function handleEndEncounter() {
    endEncounter.mutate(undefined, {
      onError: (error: Error) => {
        toast.error(error.message || 'Failed to end encounter.');
      },
    });
  }

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

          {/* Escalation strip (escalating encounters only) */}
          <EscalationStrip encounter={encounter} />

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

          {/* GM end-encounter control (#876) — confirm before the curtain falls. */}
          {showEndControl && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="destructive"
                  size="sm"
                  className="w-full"
                  disabled={endEncounter.isPending}
                  data-testid="end-encounter-trigger"
                >
                  {endEncounter.isPending ? 'Ending…' : 'End Encounter'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>End this encounter?</AlertDialogTitle>
                  <AlertDialogDescription>
                    The encounter is marked completed and the Narrator records the outcome in the
                    scene log. This cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleEndEncounter}
                    disabled={endEncounter.isPending}
                    data-testid="end-encounter-confirm"
                  >
                    End Encounter
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      )}
    </div>
  );
}
