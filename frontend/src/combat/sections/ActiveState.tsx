/**
 * ActiveState — read-only rail section showing active Clash/Ward/Break/Lock
 * cards.
 *
 * This is a purely read-only overview of the encounter's active state. The
 * interactive "commit to a clash" UX lives in YourTurn (ClashContributionRow),
 * which dispatches the real COMBAT ActionRef. ActiveState only displays status;
 * it does not own any dispatch path.
 *
 * Data source: EncounterDetail.clashes — a SerializerMethodField returning
 * ClashStateSerializer rows (id, flavor, status, progress, pc_win_threshold,
 * npc_win_threshold, npc_opponent).
 *
 * Each card shows:
 * - Clash kind label (CLASH / LOCK / WARD / BREAK)
 * - Side favored badge and opponent name
 * - Contributors list
 * - Meter (progress toward pc_win_threshold)
 */

import { cn } from '@/lib/utils';
import type { EncounterDetail } from '../types';
import type { ClashState } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ActiveStateProps {
  encounter: EncounterDetail;
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
  /** Name of the NPC this clash is against — derived from encounter.opponents. */
  opponentName?: string;
}

function ClashCard({ clash, opponentName }: ClashCardProps) {
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
      className={cn('space-y-2 rounded border p-2', colorClass)}
      data-testid={`clash-card-${clash.id}`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span
          className="text-xs font-semibold text-foreground"
          data-testid={`clash-kind-${clash.id}`}
        >
          {flavorLabel}
        </span>
        <div className="flex items-center gap-1">
          {clash.side_favored && (
            <span
              className={cn(
                'rounded px-1.5 py-0.5 text-[10px] font-medium',
                clash.side_favored === 'PC' && 'bg-emerald-500/20 text-emerald-300',
                clash.side_favored === 'NPC' && 'bg-rose-500/20 text-rose-300',
                clash.side_favored === 'EVEN' && 'bg-muted text-muted-foreground'
              )}
              data-testid={`clash-side-favored-${clash.id}`}
            >
              {clash.side_favored}
            </span>
          )}
          {opponentName !== undefined && (
            <span className="ml-2 truncate text-[10px] text-muted-foreground">
              vs {opponentName}
            </span>
          )}
        </div>
      </div>

      {/* Contributors list */}
      {clash.contributors && clash.contributors.length > 0 && (
        <ul
          className="space-y-0.5 text-[10px] text-muted-foreground"
          data-testid={`clash-contributors-${clash.id}`}
        >
          {clash.contributors.map((c) => (
            <li key={c.character_id ?? c.character_name} className="flex justify-between">
              <span className="truncate">
                {c.character_name} ({c.action_slot.toLowerCase()})
              </span>
              <span className="ml-2 font-mono">
                {c.progress_delta >= 0 ? '+' : ''}
                {c.progress_delta}
              </span>
            </li>
          ))}
        </ul>
      )}

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
        <div className="text-center font-mono text-[10px] text-muted-foreground">
          {clash.progress} / {clash.pc_win_threshold}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActiveState
// ---------------------------------------------------------------------------

export function ActiveState({ encounter, collapsed = false, onToggleCollapse }: ActiveStateProps) {
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
              opponentName={opponentById.get(clash.npc_opponent)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
