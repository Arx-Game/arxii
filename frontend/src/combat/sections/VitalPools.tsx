/**
 * VitalPools — rail section showing health, anima, and fatigue bars.
 *
 * Health: sourced from the viewer's participant row in EncounterDetail.participants.
 *   - Color shifts amber when health_percentage < 0.5.
 *   - The viewer's row is identified by an exact `character_sheet_id` match against
 *     the viewer's own sheet — not a health-presence heuristic, which picked an
 *     arbitrary row for staff/GM viewers who can see everyone's vitals. (#918)
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

import { StatBar } from '@/components/character/StatBar';
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
  /** The viewer's CharacterSheet PK — identifies their own participant row. */
  characterSheetId: number;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Find the viewer's own participant row by exact character-sheet identity.
 *
 * Replaces the former health-presence heuristic, which picked an arbitrary row
 * for staff/GM viewers who can see every participant's vitals. (#918)
 *
 * Exported: CombatTurnPanel reuses this to locate the puppeted participant for
 * the active-Audere strip. Returns undefined for observers (no matching row).
 */
export function findOwnParticipant(
  participants: Participant[],
  characterSheetId: number
): Participant | undefined {
  return participants.find((p) => p.character_sheet_id === characterSheetId);
}

// ---------------------------------------------------------------------------
// VitalPools
// ---------------------------------------------------------------------------

export function VitalPools({
  encounter,
  characterId,
  characterSheetId,
  collapsed = false,
  onToggleCollapse,
}: VitalPoolsProps) {
  const { data: animaData, isLoading: animaLoading } = useCharacterAnima(characterId);

  // Health derived from the viewer's own participant row (exact sheet match).
  const viewerParticipant = findOwnParticipant(encounter.participants, characterSheetId);
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
          <StatBar
            label="Health"
            valueText={health !== null && maxHealth !== null ? `${health} / ${maxHealth}` : '—'}
            percent={healthPct !== null ? healthPct * 100 : 0}
            fillClass={isWounded ? 'bg-amber-500' : 'bg-emerald-500'}
            testId="vital-health-bar"
          />

          {/* Anima */}
          <StatBar
            label="Anima"
            valueText={
              !animaLoading && animaCurrent !== null && animaMaximum !== null
                ? `${animaCurrent} / ${animaMaximum}`
                : animaLoading
                  ? '…'
                  : '—'
            }
            percent={
              animaCurrent !== null && animaMaximum !== null && animaMaximum > 0
                ? (animaCurrent / animaMaximum) * 100
                : 0
            }
            fillClass="bg-violet-500"
            testId="vital-anima-bar"
          />

          {/* Fatigue (Physical / Social / Mental) — real values from the
           * viewer's participant row. Hidden entirely when fatigue is null
           * (viewer lacks vitals permission). */}
          {fatigue !== null &&
            fatiguePools.map(({ key, label }) => {
              const pool = fatigue[key];
              const current = pool?.current ?? 0;
              const capacity = pool?.capacity ?? 0;
              const pct = capacity > 0 ? (current / capacity) * 100 : 0;
              return (
                <StatBar
                  key={key}
                  label={`${label} Fatigue`}
                  valueText={`${current} / ${capacity}`}
                  percent={pct}
                  fillClass="bg-orange-500"
                  testId={`vital-fatigue-${key}-bar`}
                />
              );
            })}
        </div>
      )}
    </div>
  );
}
