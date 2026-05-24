/**
 * CombatTurnPanel — top-level combat right-rail panel.
 *
 * Composed from: YourTurn (focused + passive slots, combos, clash contributions).
 * Future phases (Phase 8) add: ResonanceBudget, VitalPools, CombatantsList,
 * ActiveState, RoundFlow.
 *
 * Phase 7 of the unified-combat-ui plan.
 * See: docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §6
 */

import { cn } from '@/lib/utils';
import { useAvailableActions, useCombatEncounter } from './queries';
import { YourTurn } from './sections/YourTurn';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CombatTurnPanelProps {
  encounterId: number;
  characterId: number;
  characterSheetId: number;
}

// ---------------------------------------------------------------------------
// CombatTurnPanel
// ---------------------------------------------------------------------------

export function CombatTurnPanel({
  encounterId,
  characterId,
  characterSheetId,
}: CombatTurnPanelProps) {
  // Encounter state
  const {
    data: encounter,
    isLoading: encounterLoading,
    isError: encounterError,
  } = useCombatEncounter(encounterId);

  // Available COMBAT-backend actions for the character (includes clash refs).
  const { data: combatActions } = useAvailableActions(characterId);

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (encounterLoading) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="combat-panel-loading">
        Loading combat state…
      </div>
    );
  }

  if (encounterError || encounter === undefined) {
    return (
      <div className="p-4 text-sm text-destructive" data-testid="combat-panel-error">
        Failed to load encounter.
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isParticipant = encounter.is_participant;
  const roundNumber = encounter.round_number ?? 0;

  return (
    <div
      className={cn(
        'flex flex-col gap-4 rounded-lg border border-border bg-card p-4 shadow-sm'
      )}
      data-testid="combat-turn-panel"
    >
      {/* Panel header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-foreground">
          Your Turn — Round {roundNumber}
        </h2>
        {!isParticipant && (
          <span className="rounded border border-border bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            Observer
          </span>
        )}
      </div>

      {/* YourTurn section — only for participants */}
      {isParticipant ? (
        <YourTurn
          encounterId={encounterId}
          characterId={characterId}
          characterSheetId={characterSheetId}
          roundNumber={roundNumber}
          availableActions={combatActions}
          readOnly={false}
        />
      ) : (
        <p className="text-xs text-muted-foreground">
          You are observing this encounter.
        </p>
      )}

      {/* Phase 8 rail sections (ResonanceBudget, VitalPools, CombatantsList,
          ActiveState, RoundFlow) will be added here. */}
    </div>
  );
}
