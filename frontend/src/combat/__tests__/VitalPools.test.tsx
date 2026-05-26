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
    character_name: 'TestChar',
    status: 'active',
    health: 8,
    max_health: 10,
    character_status: 'healthy',
    available_strain: null,
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

  it('renders three fatigue placeholder bars', () => {
    const encounter = makeEncounter([makeParticipant()]);

    render(<VitalPools encounter={encounter} characterId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('vital-fatigue-physical-bar')).toBeInTheDocument();
    expect(screen.getByTestId('vital-fatigue-social-bar')).toBeInTheDocument();
    expect(screen.getByTestId('vital-fatigue-mental-bar')).toBeInTheDocument();
    // Placeholder text
    const placeholders = screen.getAllByText('(placeholder)');
    expect(placeholders).toHaveLength(3);
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
