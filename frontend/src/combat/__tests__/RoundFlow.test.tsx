/**
 * Tests for RoundFlow rail section.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// Mock the queries module — RoundFlow only consumes useEndEncounter (#876).
vi.mock('../queries', () => ({
  useEndEncounter: vi.fn(),
}));

import * as combatQueries from '../queries';
import { RoundFlow } from '../sections/RoundFlow';
import type { EncounterDetail, Participant } from '../types';

const mockedUseEndEncounter = combatQueries.useEndEncounter as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function makeParticipant(id: number, name: string): Participant {
  return {
    id,
    character_sheet_id: id + 1000,
    character_name: name,
    status: 'active',
    health: 10,
    max_health: 10,
    character_status: 'healthy',
    available_strain: null,
    fatigue: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
  };
}

function makeEncounter(
  participants: Participant[] = [],
  actedParticipantIds: number[] = [],
  roundNumber = 1,
  overrides: Partial<EncounterDetail> = {}
): EncounterDetail {
  const currentRoundActions = actedParticipantIds.map((pid) => ({ participant: pid }));
  return {
    id: 1,
    round_number: roundNumber,
    is_participant: true,
    is_gm: false,
    participants,
    opponents: [],
    current_round_actions: currentRoundActions,
    clashes: [],
    created_at: '2026-01-01T00:00:00Z',
    // Runtime sends "" until completion; the generated enum omits the blank.
    outcome: '' as EncounterDetail['outcome'],
    completed_at: null,
    escalation_curve_name: null,
    escalation_start_round: null,
    escalation_tick_narration: null,
    forced_escape: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseEndEncounter.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RoundFlow', () => {
  it('shows round number in summary line', () => {
    const encounter = makeEncounter([], [], 3);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-summary')).toHaveTextContent('Round 3');
  });

  it('shows acted/total count in summary line', () => {
    const participants = [makeParticipant(1, 'Aerande'), makeParticipant(2, 'Lyris')];
    // Only participant 1 has acted
    const encounter = makeEncounter(participants, [1], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-summary')).toHaveTextContent('1/2 acted');
  });

  it('renders one chip per participant', () => {
    const participants = [
      makeParticipant(1, 'Aerande'),
      makeParticipant(2, 'Lyris'),
      makeParticipant(3, 'Ravan'),
    ];
    const encounter = makeEncounter(participants, [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('initiative-chip-1')).toBeInTheDocument();
    expect(screen.getByTestId('initiative-chip-2')).toBeInTheDocument();
    expect(screen.getByTestId('initiative-chip-3')).toBeInTheDocument();
  });

  it('acted chip has checkmark and emerald styling', () => {
    const participants = [makeParticipant(1, 'Aerande')];
    const encounter = makeEncounter(participants, [1], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    const chip = screen.getByTestId('initiative-chip-1');
    expect(chip.className).toContain('bg-emerald-500');
    expect(chip.textContent).toContain('✓');
  });

  it('pending chip has ellipsis and muted styling', () => {
    const participants = [makeParticipant(2, 'Lyris')];
    const encounter = makeEncounter(participants, [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    const chip = screen.getByTestId('initiative-chip-2');
    expect(chip.className).toContain('text-muted-foreground');
    expect(chip.textContent).toContain('…');
  });

  it('declarations counter shows correct ratio', () => {
    const participants = [
      makeParticipant(1, 'A'),
      makeParticipant(2, 'B'),
      makeParticipant(3, 'C'),
    ];
    const encounter = makeEncounter(participants, [1, 3], 2);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('declarations-counter')).toHaveTextContent('2 / 3');
  });

  it('shows empty message when no participants', () => {
    const encounter = makeEncounter([], [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-empty')).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const encounter = makeEncounter([makeParticipant(1, 'A')], [], 1);

    render(<RoundFlow encounter={encounter} collapsed={true} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('initiative-chip-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('round-flow-summary')).not.toBeInTheDocument();
  });

  it('renders escalation strip when the encounter escalates', () => {
    const participant = { ...makeParticipant(1, 'Aria'), escalation_level: 2 };
    const encounter = {
      ...makeEncounter([participant], [], 3),
      escalation_curve_name: 'Boss Ramp',
      escalation_tick_narration: 'The air itself begins to burn.',
    };

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('escalation-strip')).toHaveTextContent('Escalation II');
    expect(screen.getByTestId('escalation-strip')).toHaveTextContent(
      'The air itself begins to burn.'
    );
  });

  it('hides escalation strip for non-escalating encounters', () => {
    const encounter = makeEncounter([makeParticipant(1, 'A')], [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('escalation-strip')).not.toBeInTheDocument();
  });
});

describe('RoundFlow — GM end-encounter control (#876)', () => {
  it('shows the End Encounter button for the GM on a live encounter', () => {
    const encounter = makeEncounter([], [], 1, { is_gm: true, status: 'declaring' });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('end-encounter-trigger')).toBeInTheDocument();
  });

  it('hides the End Encounter button for non-GMs', () => {
    const encounter = makeEncounter([], [], 1, { is_gm: false, status: 'declaring' });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('end-encounter-trigger')).not.toBeInTheDocument();
  });

  it('hides the End Encounter button on a completed encounter', () => {
    const encounter = makeEncounter([], [], 1, {
      is_gm: true,
      status: 'completed',
      outcome: 'abandoned',
    });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('end-encounter-trigger')).not.toBeInTheDocument();
  });

  it('requires confirmation before firing the mutation', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    mockedUseEndEncounter.mockReturnValue({ mutate, isPending: false });
    const encounter = makeEncounter([], [], 1, { is_gm: true, status: 'declaring' });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('end-encounter-trigger'));
    // Confirm dialog is open; nothing fired yet.
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('end-encounter-confirm'));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('does not fire the mutation when the dialog is cancelled', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    mockedUseEndEncounter.mockReturnValue({ mutate, isPending: false });
    const encounter = makeEncounter([], [], 1, { is_gm: true, status: 'declaring' });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('end-encounter-trigger'));
    await user.click(await screen.findByRole('button', { name: /cancel/i }));

    expect(mutate).not.toHaveBeenCalled();
  });

  it('disables the trigger while the mutation is pending', () => {
    mockedUseEndEncounter.mockReturnValue({ mutate: vi.fn(), isPending: true });
    const encounter = makeEncounter([], [], 1, { is_gm: true, status: 'declaring' });

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    const trigger = screen.getByTestId('end-encounter-trigger');
    expect(trigger).toBeDisabled();
    expect(trigger).toHaveTextContent('Ending…');
  });
});
