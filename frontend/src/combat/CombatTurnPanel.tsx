/**
 * CombatTurnPanel — top-level combat right-rail panel.
 *
 * Composed from all six rail sections (Task 8.6) in spec §2 order:
 *   YourTurn → ResonanceBudget → VitalPools → CombatantsList → ActiveState → RoundFlow
 *
 * Each section is collapsible via a ▾ header chevron. Collapse state is
 * held locally in a useState Record to persist across renders within the session.
 *
 * Phase 7 (scaffold) + Phase 8 (rail sections) of the unified-combat-ui plan.
 * See: docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §2
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useAvailableActions, useCombatEncounter } from './queries';
import { YourTurn } from './sections/YourTurn';
import { ResonanceBudget } from './sections/ResonanceBudget';
import { VitalPools } from './sections/VitalPools';
import { CombatantsList } from './sections/CombatantsList';
import { ActiveState } from './sections/ActiveState';
import { RoundFlow } from './sections/RoundFlow';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CombatTurnPanelProps {
  encounterId: number;
  characterId: number;
  characterSheetId: number;
}

// ---------------------------------------------------------------------------
// Section names (for collapse state keying)
// ---------------------------------------------------------------------------

type SectionName =
  | 'yourTurn'
  | 'resonanceBudget'
  | 'vitalPools'
  | 'combatantsList'
  | 'activeState'
  | 'roundFlow';

const DEFAULT_COLLAPSE_STATE: Record<SectionName, boolean> = {
  yourTurn: false,
  resonanceBudget: false,
  vitalPools: false,
  combatantsList: false,
  activeState: false,
  roundFlow: false,
};

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

  // Collapse state — all sections start expanded.
  const [collapsed, setCollapsed] = useState<Record<SectionName, boolean>>(DEFAULT_COLLAPSE_STATE);

  function toggleSection(section: SectionName) {
    setCollapsed((prev) => ({ ...prev, [section]: !prev[section] }));
  }

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
      className={cn('flex flex-col gap-3 rounded-lg border border-border bg-card p-3 shadow-sm')}
      data-testid="combat-turn-panel"
    >
      {/* Panel header — round number + observer badge */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-foreground">Your Turn — Round {roundNumber}</h2>
        {!isParticipant && (
          <span className="rounded border border-border bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            Observer
          </span>
        )}
      </div>

      {/* §2 — Section order: YourTurn → ResonanceBudget → VitalPools →
          CombatantsList → ActiveState → RoundFlow */}

      {/* 1. YourTurn — only for participants */}
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
        <p className="text-xs text-muted-foreground">You are observing this encounter.</p>
      )}

      {/* 2. ResonanceBudget */}
      <ResonanceBudget
        characterSheetId={characterSheetId}
        collapsed={collapsed.resonanceBudget}
        onToggleCollapse={() => toggleSection('resonanceBudget')}
        data-testid="section-resonance-budget"
      />

      {/* 3. VitalPools */}
      <VitalPools
        encounter={encounter}
        characterId={characterId}
        collapsed={collapsed.vitalPools}
        onToggleCollapse={() => toggleSection('vitalPools')}
        data-testid="section-vital-pools"
      />

      {/* 4. CombatantsList */}
      <CombatantsList
        encounter={encounter}
        collapsed={collapsed.combatantsList}
        onToggleCollapse={() => toggleSection('combatantsList')}
        data-testid="section-combatants-list"
      />

      {/* 5. ActiveState */}
      <ActiveState
        encounter={encounter}
        collapsed={collapsed.activeState}
        onToggleCollapse={() => toggleSection('activeState')}
        data-testid="section-active-state"
      />

      {/* 6. RoundFlow */}
      <RoundFlow
        encounter={encounter}
        collapsed={collapsed.roundFlow}
        onToggleCollapse={() => toggleSection('roundFlow')}
        data-testid="section-round-flow"
      />
    </div>
  );
}
