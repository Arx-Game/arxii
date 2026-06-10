/**
 * VitalPools — rail section showing health, anima, and fatigue bars.
 *
 * Health: sourced from the viewer's participant row in EncounterDetail.participants.
 *   - Color shifts amber when health_percentage < 0.5.
 *   - Identified by finding the participant with non-null health (the viewer's own
 *     vitals are only returned for the viewer; other participants' health is hidden).
 *   - If viewer is staff/GM, health is visible for all — we fall back to the first
 *     participant whose `health` field is non-null.
 *
 * Anima: sourced from useCharacterAnima(characterId).
 *   - characterId is the ObjectDB PK (same as what CharacterAnimaFilter uses).
 *
 * Fatigue (Physical / Social / Mental): sourced from the viewer's participant
 *   row's `fatigue` field (the same row that supplies health). Each pool is
 *   `{ current, capacity }`. When `fatigue` is null (viewer lacks vitals
 *   permission) the fatigue bars are hidden entirely — no fake numbers. (#552)
 *
 * Phase 8, Task 8.2 — unified-combat-ui plan.
 */

import { cn } from '@/lib/utils';
import { useCharacterAnima } from '@/magic/queries';
import type { EncounterDetail, Participant } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface VitalPoolsProps {
  encounter: EncounterDetail;
  /** The viewer's character ObjectDB PK — used to query CharacterAnima. */
  characterId: number;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Find the viewer's participant row.
 *
 * The API only returns health/max_health for the viewer's own character.
 * We detect "own" by finding the first participant with a non-null health value.
 * If none have health (observer mode or all-null), returns undefined.
 *
 * Exported: CombatTurnPanel reuses this to locate the puppeted participant for
 * the active-Audere strip (Participant exposes no character/sheet id field).
 */
export function findViewerParticipant(participants: Participant[]): Participant | undefined {
  return participants.find((p) => p.health !== null && p.health !== undefined);
}

// ---------------------------------------------------------------------------
// BarRow — labelled horizontal bar
// ---------------------------------------------------------------------------

interface BarRowProps {
  label: string;
  current: number;
  maximum: number;
  /** Tailwind fill class, e.g. 'bg-primary' or 'bg-amber-500'. */
  fillClass?: string;
  testId?: string;
}

function BarRow({ label, current, maximum, fillClass = 'bg-primary', testId }: BarRowProps) {
  const pct = maximum > 0 ? Math.min(100, (current / maximum) * 100) : 0;
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-foreground">{label}</span>
        <span className="font-mono text-xs text-foreground">
          {current}
          <span className="text-muted-foreground"> / {maximum}</span>
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', fillClass)}
          style={{ width: `${pct}%` }}
          data-testid={testId !== undefined ? `${testId}-fill` : undefined}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// VitalPools
// ---------------------------------------------------------------------------

export function VitalPools({
  encounter,
  characterId,
  collapsed = false,
  onToggleCollapse,
}: VitalPoolsProps) {
  const { data: animaData, isLoading: animaLoading } = useCharacterAnima(characterId);

  // Health derived from the viewer's participant row.
  const viewerParticipant = findViewerParticipant(encounter.participants);
  const health = viewerParticipant?.health ?? null;
  const maxHealth = viewerParticipant?.max_health ?? null;
  const healthPct =
    health !== null && maxHealth !== null && maxHealth > 0 ? health / maxHealth : null;
  const isWounded = healthPct !== null && healthPct < 0.5;

  // Anima from the CharacterAnima record.
  const animaCurrent = animaData?.current ?? null;
  const animaMaximum = animaData?.maximum ?? null;

  // Fatigue pools come from the same viewer participant row. Null when the
  // viewer lacks vitals permission — in that case we render no fatigue bars.
  const fatigue = viewerParticipant?.fatigue ?? null;
  const fatiguePools: { key: string; label: string }[] = [
    { key: 'physical', label: 'Physical' },
    { key: 'social', label: 'Social' },
    { key: 'mental', label: 'Mental' },
  ];

  return (
    <div className="rounded-md border border-border bg-card" data-testid="vital-pools-section">
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="vital-pools-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Vital Pools
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
          {/* Health */}
          {health !== null && maxHealth !== null ? (
            <BarRow
              label="Health"
              current={health}
              maximum={maxHealth}
              fillClass={isWounded ? 'bg-amber-500' : 'bg-emerald-500'}
              testId="vital-health-bar"
            />
          ) : (
            <div className="space-y-1" data-testid="vital-health-bar">
              <div className="flex items-center justify-between">
                <span className="text-xs text-foreground">Health</span>
                <span className="text-xs text-muted-foreground">—</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted" />
            </div>
          )}

          {/* Anima */}
          {!animaLoading && animaCurrent !== null && animaMaximum !== null ? (
            <BarRow
              label="Anima"
              current={animaCurrent}
              maximum={animaMaximum}
              fillClass="bg-violet-500"
              testId="vital-anima-bar"
            />
          ) : (
            <div className="space-y-1" data-testid="vital-anima-bar">
              <div className="flex items-center justify-between">
                <span className="text-xs text-foreground">Anima</span>
                <span className="text-xs text-muted-foreground">{animaLoading ? '…' : '—'}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted" />
            </div>
          )}

          {/* Fatigue (Physical / Social / Mental) — real values from the
           * viewer's participant row. Hidden entirely when fatigue is null
           * (viewer lacks vitals permission). */}
          {fatigue !== null &&
            fatiguePools.map(({ key, label }) => {
              const pool = fatigue[key];
              const current = pool?.current ?? 0;
              const capacity = pool?.capacity ?? 0;
              const pct = capacity > 0 ? Math.min(100, Math.max(0, (current / capacity) * 100)) : 0;
              const testId = `vital-fatigue-${key}-bar`;
              return (
                <div key={key} className="space-y-1" data-testid={testId}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-foreground">{label} Fatigue</span>
                    <span className="font-mono text-xs text-foreground">
                      {current}
                      <span className="text-muted-foreground"> / {capacity}</span>
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-orange-500 transition-all"
                      style={{ width: `${pct}%` }}
                      data-testid={`${testId}-fill`}
                    />
                  </div>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
