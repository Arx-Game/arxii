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
import { AudereOfferGate } from '@/magic/components/AudereOfferGate';
import { AudereMajoraOfferGate } from '@/magic/components/AudereMajoraOfferGate';
import { useAvailableActions, useCombatEncounter, useConsequenceOutcomes } from './queries';
import { YourTurn } from './sections/YourTurn';
import { ResonanceBudget } from './sections/ResonanceBudget';
import { VitalPools, findViewerParticipant } from './sections/VitalPools';
import { CombatantsList } from './sections/CombatantsList';
import { ActiveState } from './sections/ActiveState';
import { RoundFlow } from './sections/RoundFlow';
import { EncounterOutcomeBanner } from './components/EncounterOutcomeBanner';
import { OutcomeRoulette } from './OutcomeRoulette';
import type { OutcomeDisplayRow } from './api';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

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
  | 'roundFlow'
  | 'outcomeRoulette';

const DEFAULT_COLLAPSE_STATE: Record<SectionName, boolean> = {
  yourTurn: false,
  resonanceBudget: false,
  vitalPools: false,
  combatantsList: false,
  activeState: false,
  roundFlow: false,
  outcomeRoulette: false,
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

  // Most recent consequence outcome for this character scoped to the current encounter.
  const { data: consequenceOutcomes } = useConsequenceOutcomes({
    character: characterId,
    encounter: encounterId,
    page_size: 1,
  });
  const latestOutcome = consequenceOutcomes?.[0] ?? null;

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
  // Completed encounter — outcome banner replaces the live rail sections (#876)
  // ---------------------------------------------------------------------------

  if (encounter.status === 'completed') {
    // Pre-#876 rows completed without a recorded outcome (the API sends "" —
    // the generated enum omits the blank); fall back to "abandoned" so the
    // banner always names a result.
    const outcome: string = encounter.outcome || 'abandoned';
    return (
      <div
        className={cn('flex flex-col gap-3 rounded-lg border border-border bg-card p-3 shadow-sm')}
        data-testid="combat-turn-panel"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-foreground">
            Encounter Concluded — Round {encounter.round_number ?? 0}
          </h2>
        </div>
        <EncounterOutcomeBanner outcome={outcome} />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isParticipant = encounter.is_participant;
  const roundNumber = encounter.round_number ?? 0;

  // Audere active strip — the puppeted participant's row (Participant exposes
  // no character/sheet id, so reuse VitalPools' owner-vitals heuristic) carries
  // the Audere condition in active_conditions while the breakthrough is live.
  // active_conditions entries are ConditionInstances typed loosely on the
  // generated schema (SerializerMethodField); cast at the boundary.
  const viewerParticipant = findViewerParticipant(encounter.participants);
  const isAudereActive = ((viewerParticipant?.active_conditions ?? []) as ConditionInstance[]).some(
    (c) => c.name === 'Audere'
  );

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

      {/* 0. Audere offer gate — the most dramatic prompt in combat (#873).
          Renders null unless a pending offer exists for this character. */}
      <AudereOfferGate
        characterSheetId={characterSheetId}
        characterId={characterId}
        encounterId={encounterId}
      />
      {/* 0b. Audere Majora crossing offer gate (#543).
          Renders null unless a pending crossing offer exists for this character. */}
      <AudereMajoraOfferGate
        characterSheetId={characterSheetId}
        characterId={characterId}
        encounterId={encounterId}
      />

      {/* Active-Audere strip — visible while the breakthrough condition runs. */}
      {isAudereActive ? (
        <div
          className="rounded-md border border-fuchsia-500/60 bg-fuchsia-950/40 px-3 py-1.5 text-center text-xs font-bold uppercase tracking-[0.3em] text-fuchsia-300"
          data-testid="audere-active-strip"
        >
          Audere
        </div>
      ) : null}

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
          encounter={encounter}
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

      {/* 7. OutcomeRoulette — most recent consequence outcome for this character */}
      {latestOutcome !== null && (
        <div
          className="rounded-md border border-border bg-card"
          data-testid="outcome-roulette-section"
        >
          <button
            type="button"
            onClick={() => toggleSection('outcomeRoulette')}
            className="flex w-full items-center justify-between px-3 py-2 text-left"
            aria-expanded={!collapsed.outcomeRoulette}
            data-testid="outcome-roulette-toggle"
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Last Outcome
            </span>
            <span
              className={cn(
                'text-muted-foreground transition-transform',
                collapsed.outcomeRoulette ? '-rotate-90' : 'rotate-0'
              )}
              aria-hidden="true"
            >
              ▾
            </span>
          </button>
          {!collapsed.outcomeRoulette && (
            <div className="border-t border-border px-3 py-2">
              <OutcomeRoulette
                outcomeDisplay={latestOutcome.outcome_display as unknown as OutcomeDisplayRow[]}
                modifiers={latestOutcome.modifiers}
                modifierTotal={latestOutcome.modifier_total}
                summary={latestOutcome.summary}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
