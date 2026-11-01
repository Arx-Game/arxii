/**
 * Tests for the Pressure rail section (#4738): intensity, control, and the Fury chip.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Pressure } from '../sections/Pressure';
import type { EncounterDetail, Participant } from '../types';

function makeParticipant(overrides: Partial<Participant> = {}): Participant {
  return {
    id: 1,
    character_sheet_id: 1001,
    character_name: 'TestChar',
    status: 'active',
    health: 8,
    max_health: 10,
    character_status: 'healthy',
    available_strain: null,
    fatigue: {
      physical: { current: 3, capacity: 12 },
      social: { current: 1, capacity: 9 },
      mental: { current: 4, capacity: 11 },
    },
    active_conditions: [],
    audere_state: null,
    thumbnail_url: '',
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
    fury_control_surrendered: null,
    current_square: null,
    current_position: null,
    aftermath: null,
    reactions_used: null,
    dodge_plan: null,
    dig_deep: null,
    strike_weapons: null,
    ...overrides,
  };
}

function makeEncounter(participants: Participant[] = []): EncounterDetail {
  return {
    id: 1,
    scene: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    objective: null,
    standoff: null,
    gm_standoff: null,
    standoff_summary: null,
    participants,
    opponents: [],
    current_round_actions: [],
    clashes: [],
    engagement_locks: [],
    marks: [],
    pending_attacks: [],
    created_at: '2026-01-01T00:00:00Z',
    outcome: '',
    completed_at: null,
    escalation_curve_name: null,
    escalation_start_round: null,
    escalation_tick_narration: null,
    forced_escape: false,
    resolution_order: [],
    position_adjacency: [],
    position_nodes: [],
    position_edges: [],
    held_positions: [],
    volatile_objects: [],
    is_lethal: false,
    duel_winner: null,
    surge_beats: [],
  };
}

describe('Pressure', () => {
  it("shows the viewer's own intensity and control", () => {
    render(
      <Pressure
        encounter={makeEncounter([
          makeParticipant({ intensity_modifier: 8, control_modifier: -6 }),
          makeParticipant({
            id: 2,
            character_sheet_id: 2002,
            intensity_modifier: 30,
            control_modifier: 4,
          }),
        ])}
        characterSheetId={1001}
      />
    );
    expect(screen.getByTestId('pressure-intensity')).toHaveTextContent('Intensity+8');
    expect(screen.getByTestId('pressure-control')).toHaveTextContent('Control-6');
  });

  it('shows the Fury chip once control has been surrendered', () => {
    render(
      <Pressure
        encounter={makeEncounter([
          makeParticipant({
            intensity_modifier: 8,
            control_modifier: -6,
            fury_control_surrendered: 6,
          }),
        ])}
        characterSheetId={1001}
      />
    );
    const chip = screen.getByTestId('pressure-fury-chip');
    expect(chip).toHaveTextContent('Fury: surrendered 6 control');
    // A light-theme colour and a dark one: a single pale red was unreadable on a white card.
    expect(chip).toHaveClass('text-red-700', 'dark:text-red-400');
  });

  it('shows no Fury chip when nothing was surrendered', () => {
    render(
      <Pressure
        encounter={makeEncounter([
          makeParticipant({
            intensity_modifier: 0,
            control_modifier: 0,
            fury_control_surrendered: 0,
          }),
        ])}
        characterSheetId={1001}
      />
    );
    expect(screen.getByTestId('pressure-section')).toBeInTheDocument();
    expect(screen.queryByTestId('pressure-fury-chip')).not.toBeInTheDocument();
  });

  it('renders nothing without a combat engagement', () => {
    render(<Pressure encounter={makeEncounter([makeParticipant()])} characterSheetId={1001} />);
    expect(screen.queryByTestId('pressure-section')).not.toBeInTheDocument();
  });
});
