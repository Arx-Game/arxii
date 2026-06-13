/**
 * Tests for VitalPools rail section.
 *
 * Mocks useCharacterAnima. Provides encounter with participants.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useCharacterAnima: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { VitalPools } from '../sections/VitalPools';
import type { EncounterDetail, Participant } from '../types';

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

const mockedUseCharacterAnima = magicQueries.useCharacterAnima as ReturnType<typeof vi.fn>;

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
    thumbnail_url: '',
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
    ...overrides,
  };
}

function makeEncounter(participants: Participant[] = []): EncounterDetail {
  return {
    id: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants,
    opponents: [],
    current_round_actions: [],
    clashes: [],
    created_at: '2026-01-01T00:00:00Z',
    // Runtime sends "" until completion; the generated enum omits the blank.
    outcome: '' as EncounterDetail['outcome'],
    completed_at: null,
    escalation_curve_name: null,
    escalation_start_round: null,
    escalation_tick_narration: null,
    forced_escape: false,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseCharacterAnima.mockReturnValue({
    data: { id: 1, character: 10, current: 5, maximum: 10, last_recovery: null },
    isLoading: false,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('VitalPools', () => {
  it('renders the health bar with correct values', () => {
    const encounter = makeEncounter([makeParticipant({ health: 8, max_health: 10 })]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('vital-health-bar')).toBeInTheDocument();
    expect(screen.getByText('Health')).toBeInTheDocument();
    // 8/10 visible
    expect(screen.getByText('8')).toBeInTheDocument();
  });

  it('shows amber fill when health is below 50%', () => {
    const encounter = makeEncounter([makeParticipant({ health: 4, max_health: 10 })]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    // health = 4/10 = 40% → wounded (amber)
    const fillBar = screen.getByTestId('vital-health-bar-fill');
    expect(fillBar.className).toContain('bg-amber-500');
  });

  it('shows green fill when health is at or above 50%', () => {
    const encounter = makeEncounter([makeParticipant({ health: 6, max_health: 10 })]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    const fillBar = screen.getByTestId('vital-health-bar-fill');
    expect(fillBar.className).toContain('bg-emerald-500');
  });

  it('renders the anima bar with correct values', () => {
    const encounter = makeEncounter([makeParticipant()]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('vital-anima-bar')).toBeInTheDocument();
    expect(screen.getByText('Anima')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders three fatigue bars with real values', () => {
    const encounter = makeEncounter([
      makeParticipant({
        fatigue: {
          physical: { current: 3, capacity: 12 },
          social: { current: 1, capacity: 8 },
          mental: { current: 5, capacity: 10 },
        },
      }),
    ]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    const physical = screen.getByTestId('vital-fatigue-physical-bar');
    const social = screen.getByTestId('vital-fatigue-social-bar');
    const mental = screen.getByTestId('vital-fatigue-mental-bar');
    expect(physical).toBeInTheDocument();
    expect(social).toBeInTheDocument();
    expect(mental).toBeInTheDocument();

    // Real values, not the 0/10 placeholder.
    expect(physical).toHaveTextContent('3');
    expect(physical).toHaveTextContent('/ 12');
    expect(social).toHaveTextContent('/ 8');
    expect(mental).toHaveTextContent('/ 10');
  });

  it('no longer renders the placeholder affordances', () => {
    const encounter = makeEncounter([makeParticipant()]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByText('(placeholder)')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Fatigue tracking not yet implemented')).not.toBeInTheDocument();
  });

  it('clamps the fatigue fill width to [0, 100%]', () => {
    const encounter = makeEncounter([
      makeParticipant({
        fatigue: {
          physical: { current: 20, capacity: 10 }, // over capacity
          social: { current: 0, capacity: 0 }, // divide-by-zero guard
          mental: { current: 5, capacity: 10 },
        },
      }),
    ]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    const physicalFill = screen.getByTestId('vital-fatigue-physical-bar-fill');
    expect(physicalFill).toHaveStyle({ width: '100%' });
    const socialFill = screen.getByTestId('vital-fatigue-social-bar-fill');
    expect(socialFill).toHaveStyle({ width: '0%' });
  });

  it('hides fatigue bars when fatigue is null (no vitals permission)', () => {
    const encounter = makeEncounter([makeParticipant({ fatigue: null })]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('vital-fatigue-physical-bar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('vital-fatigue-social-bar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('vital-fatigue-mental-bar')).not.toBeInTheDocument();
    // No fake numbers.
    expect(screen.queryByText('0 / 10')).not.toBeInTheDocument();
  });

  it('shows dash when no participant health is available', () => {
    const encounter = makeEncounter([makeParticipant({ health: null, max_health: null })]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('vital-health-bar')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const encounter = makeEncounter([makeParticipant()]);

    render(<VitalPools encounter={encounter} characterId={10} collapsed={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('vital-health-bar')).not.toBeInTheDocument();
  });
});
