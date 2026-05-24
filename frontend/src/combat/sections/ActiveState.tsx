/**
 * ActiveState — rail section showing active Clash/Ward/Break/Lock cards.
 *
 * Data source: EncounterDetail.clashes — a SerializerMethodField returning
 * ClashStateSerializer rows (id, flavor, status, progress, pc_win_threshold,
 * npc_win_threshold, npc_opponent). Added in Phase 8, Task 8.4.
 *
 * Each card shows:
 * - Clash kind label (CLASH / LOCK / WARD / BREAK)
 * - Meter (progress toward pc_win_threshold)
 * - Commit / Lend buttons (stubbed — actual dispatch wired in Phase 11
 *   when the full combat layout composes; see TODO below)
 *
 * TODO(phase-11): wire onCommitClick and onLendClick to actual
 * useDispatchPlayerAction calls in CombatScenePage. For Phase 8 these
 * are stub callbacks so the UI renders without dispatch logic.
 *
 * Phase 8, Task 8.4 — unified-combat-ui plan.
 */

import { cn } from '@/lib/utils';
import type { EncounterDetail } from '../types';
import type { ClashState } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ActiveStateProps {
  encounter: EncounterDetail;
  /** Called when user clicks "Commit to clash" — dispatch wired in Phase 11. */
  onCommitClick?: (clashId: number) => void;
  /** Called when user clicks "Lend to clash" — dispatch wired in Phase 11. */
  onLendClick?: (clashId: number) => void;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// Flavor labels and colors
// ---------------------------------------------------------------------------

const FLAVOR_LABEL: Record<ClashState['flavor'], string> = {
  CLASH: 'Clash',
  LOCK: 'Lock',
  WARD: 'Ward',
  BREAK: 'Break',
};

const FLAVOR_COLOR: Record<ClashState['flavor'], string> = {
  CLASH: 'border-destructive/40 bg-destructive/5',
  LOCK: 'border-amber-500/40 bg-amber-500/5',
  WARD: 'border-blue-500/40 bg-blue-500/5',
  BREAK: 'border-violet-500/40 bg-violet-500/5',
};

// ---------------------------------------------------------------------------
// ClashCard — renders one active Clash
// ---------------------------------------------------------------------------

interface ClashCardProps {
  clash: ClashState;
  onCommitClick?: (clashId: number) => void;
  onLendClick?: (clashId: number) => void;
  /** Name of the NPC this clash is against — derived from encounter.opponents. */
  opponentName?: string;
}

function ClashCard({ clash, onCommitClick, onLendClick, opponentName }: ClashCardProps) {
  // Meter: progress toward pc_win_threshold.
  // progress can be negative (NPC side winning) — clamp for display.
  const isClash = clash.flavor === 'CLASH';
  const meterMin = isClash && clash.npc_win_threshold !== null ? clash.npc_win_threshold : 0;
  const meterMax = clash.pc_win_threshold;
  const meterRange = meterMax - meterMin;
  const meterPct =
    meterRange > 0 ? Math.min(100, ((clash.progress - meterMin) / meterRange) * 100) : 50;

  const flavorLabel = FLAVOR_LABEL[clash.flavor];
  const colorClass = FLAVOR_COLOR[clash.flavor];

  return (
    <div
      className={cn('rounded border p-2 space-y-2', colorClass)}
      data-testid={`clash-card-${clash.id}`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground" data-testid={`clash-kind-${clash.id}`}>
          {flavorLabel}
        </span>
        {opponentName !== undefined && (
          <span className="text-[10px] text-muted-foreground truncate ml-2">
            vs {opponentName}
          </span>
        )}
      </div>

      {/* Meter */}
      <div className="space-y-0.5">
        <div className="flex justify-between text-[10px] text-muted-foreground">
          {isClash && clash.npc_win_threshold !== null && (
            <span>NPC {clash.npc_win_threshold}</span>
          )}
          <span className="ml-auto">PC {clash.pc_win_threshold}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${meterPct}%` }}
            data-testid={`clash-meter-${clash.id}`}
          />
        </div>
        <div className="text-center text-[10px] font-mono text-muted-foreground">
          {clash.progress} / {clash.pc_win_threshold}
        </div>
      </div>

      {/* Action buttons — stub dispatch, wired in Phase 11 */}
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={() => onCommitClick?.(clash.id)}
          className={cn(
            'flex-1 rounded border border-primary/40 bg-primary/5 px-2 py-1 text-xs font-medium',
            'text-primary hover:bg-primary/10 transition-colors'
          )}
          data-testid={`clash-commit-btn-${clash.id}`}
          // TODO(phase-11): dispatch wiring — currently calls the stub callback.
          // Phase 11 will wire this to useDispatchPlayerAction with the clash ref.
        >
          Commit
        </button>
        <button
          type="button"
          onClick={() => onLendClick?.(clash.id)}
          className={cn(
            'flex-1 rounded border border-border bg-background px-2 py-1 text-xs font-medium',
            'text-muted-foreground hover:bg-accent/30 transition-colors'
          )}
          data-testid={`clash-lend-btn-${clash.id}`}
          // TODO(phase-11): dispatch wiring — currently calls the stub callback.
        >
          Lend
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActiveState
// ---------------------------------------------------------------------------

export function ActiveState({
  encounter,
  onCommitClick,
  onLendClick,
  collapsed = false,
  onToggleCollapse,
}: ActiveStateProps) {
  // The generated schema types clashes as {[key: string]: unknown}[] —
  // we cast to our local ClashState[] since ClashStateSerializer produces
  // exactly that shape.
  const clashes = encounter.clashes as unknown as ClashState[];

  // Build a quick opponent lookup by id.
  const opponentById = new Map(encounter.opponents.map((o) => [o.id, o.name]));

  return (
    <div className="rounded-md border border-border bg-card" data-testid="active-state-section">
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="active-state-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Active State
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
        <div className="space-y-2 border-t border-border px-3 py-2">
          {clashes.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="active-state-empty">
              No active clashes.
            </p>
          )}
          {clashes.map((clash) => (
            <ClashCard
              key={clash.id}
              clash={clash}
              onCommitClick={onCommitClick}
              onLendClick={onLendClick}
              opponentName={opponentById.get(clash.npc_opponent)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
