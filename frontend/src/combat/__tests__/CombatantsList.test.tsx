/**
 * Tests for CombatantsList rail section.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

import { deepLinkModalSlice } from '@/store/deepLinkModalSlice';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

// ---------------------------------------------------------------------------
// Module mocks — PersonaAvatar is used; stub it to simplify tests
// ---------------------------------------------------------------------------

vi.mock('@/components/PersonaAvatar', () => ({
  PersonaAvatar: ({
    source,
  }: {
    source: { name: string; thumbnailUrl?: string | null; thumbnailMediaUrl?: string | null };
  }) => {
    const url = source.thumbnailMediaUrl ?? source.thumbnailUrl ?? null;
    return url ? (
      <span data-testid="persona-avatar">
        <img src={url} alt={source.name} />
      </span>
    ) : (
      <span data-testid="persona-avatar">{source.name[0].toUpperCase()}</span>
    );
  },
}));

import { CombatantsList } from '../sections/CombatantsList';
import type { EncounterDetail, Participant, Opponent } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeStore() {
  return configureStore({ reducer: { deepLinkModal: deepLinkModalSlice.reducer } });
}

function createWrapper(store: ReturnType<typeof makeStore> = makeStore()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    );
  };
}

function makeCondition(overrides: Partial<ConditionInstance> = {}): ConditionInstance {
  return {
    id: 7,
    name: 'Bleeding Out',
    icon: '🩸',
    color_hex: '#cc0000',
    display_priority: 10,
    ...overrides,
  } as unknown as ConditionInstance;
}

function makeParticipant(overrides: Partial<Participant> = {}): Participant {
  return {
    id: 1,
    character_sheet_id: 1001,
    character_name: 'Aerande',
    status: 'active',
    health: 8,
    max_health: 10,
    character_status: 'healthy',
    available_strain: null,
    fatigue: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    ...overrides,
  };
}

function makeOpponent(overrides: Partial<Opponent> = {}): Opponent {
  return {
    id: 1,
    name: 'Mire Knight',
    tier: 'elite',
    health: 5,
    max_health: 10,
    soak_value: null,
    probing_threshold: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    ...overrides,
  };
}

function makeEncounter(
  participants: Participant[] = [],
  opponents: Opponent[] = []
): EncounterDetail {
  return {
    id: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants,
    opponents,
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
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CombatantsList', () => {
  it('renders PC rows from participants', () => {
    const encounter = makeEncounter(
      [
        makeParticipant({ id: 1, character_name: 'Aerande' }),
        makeParticipant({ id: 2, character_name: 'Lyris' }),
      ],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('participant-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('participant-row-2')).toBeInTheDocument();
    expect(screen.getByText('Aerande')).toBeInTheDocument();
    expect(screen.getByText('Lyris')).toBeInTheDocument();
  });

  it('renders NPC rows from opponents', () => {
    const encounter = makeEncounter(
      [],
      [
        makeOpponent({ id: 10, name: 'Mire Knight' }),
        makeOpponent({ id: 11, name: 'Shadow Archer' }),
      ]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('opponent-row-10')).toBeInTheDocument();
    expect(screen.getByTestId('opponent-row-11')).toBeInTheDocument();
    expect(screen.getByText('Mire Knight')).toBeInTheDocument();
    expect(screen.getByText('Shadow Archer')).toBeInTheDocument();
  });

  it('renders an opponent portrait when a thumbnail media URL is present', () => {
    const encounter = makeEncounter(
      [],
      [
        makeOpponent({
          id: 21,
          name: 'Ogre',
          thumbnail_media_url: 'https://media.example/ogre.png',
        }),
      ]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('opponent-row-21');
    const img = within(row).getByRole('img');
    expect(img).toHaveAttribute('src', 'https://media.example/ogre.png');
  });

  it('renders a PC portrait when the primary persona has a thumbnail media URL', () => {
    const encounter = makeEncounter(
      [
        makeParticipant({
          id: 31,
          character_name: 'Aerande',
          thumbnail_media_url: 'https://media.example/aerande.png',
        }),
      ],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-31');
    const img = within(row).getByRole('img');
    expect(img).toHaveAttribute('src', 'https://media.example/aerande.png');
  });

  it('renders an initial-letter avatar for a PC without a thumbnail', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 32, character_name: 'Lyris', thumbnail_media_url: null })],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-32');
    expect(within(row).queryByRole('img')).not.toBeInTheDocument();
    expect(within(row).getByText('L')).toBeInTheDocument();
  });

  it('renders an initial-letter avatar for an opponent without a thumbnail', () => {
    const encounter = makeEncounter(
      [],
      [
        makeOpponent({
          id: 22,
          name: 'Wraith',
          thumbnail_media_url: null,
        }),
      ]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('opponent-row-22');
    expect(within(row).queryByRole('img')).not.toBeInTheDocument();
    expect(within(row).getByText('W')).toBeInTheDocument();
  });

  it('NPC rows have destructive styling to distinguish from PCs', () => {
    const encounter = makeEncounter([makeParticipant({ id: 1 })], [makeOpponent({ id: 10 })]);

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const pcRow = screen.getByTestId('participant-row-1');
    const npcRow = screen.getByTestId('opponent-row-10');

    // NPC rows have border-destructive/30 class; PC rows do not
    expect(npcRow.className).toContain('border-destructive');
    expect(pcRow.className).not.toContain('border-destructive');
  });

  it('HP bar shows correct percentage for PC', () => {
    const encounter = makeEncounter([makeParticipant({ id: 1, health: 5, max_health: 10 })], []);

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-1');
    // Inside the row there should be a fill bar with width=50%
    const fill = row.querySelector('[style*="width: 50%"]');
    expect(fill).not.toBeNull();
  });

  it('renders empty message when no combatants', () => {
    const encounter = makeEncounter([], []);

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combatants-empty')).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const encounter = makeEncounter([makeParticipant({ id: 1 })], []);

    render(<CombatantsList encounter={encounter} collapsed={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('participant-row-1')).not.toBeInTheDocument();
  });

  it('renders condition badges for a participant with active_conditions', () => {
    const encounter = makeEncounter(
      [
        makeParticipant({
          id: 1,
          active_conditions: [makeCondition({ id: 7, name: 'Bleeding Out' })],
        }) as Participant,
      ],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-1');
    expect(within(row).getByRole('button', { name: /Bleeding Out/i })).toBeInTheDocument();
  });

  it('renders condition badges for an opponent with active_conditions', () => {
    const encounter = makeEncounter(
      [],
      [
        makeOpponent({
          id: 10,
          active_conditions: [makeCondition({ id: 9, name: 'Stunned' })],
        }) as Opponent,
      ]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('opponent-row-10');
    expect(within(row).getByRole('button', { name: /Stunned/i })).toBeInTheDocument();
  });

  it('renders no condition badges when active_conditions is empty', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 1, active_conditions: [] }) as Participant],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-1');
    expect(within(row).queryByTestId('condition-row')).not.toBeInTheDocument();
  });

  it('clicking a condition badge dispatches openDeepLink with the condition id', async () => {
    const store = makeStore();
    const user = userEvent.setup();
    const encounter = makeEncounter(
      [
        makeParticipant({
          id: 1,
          active_conditions: [makeCondition({ id: 7, name: 'Bleeding Out' })],
        }) as Participant,
      ],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper(store) });

    await user.click(screen.getByRole('button', { name: /Bleeding Out/i }));

    expect(store.getState().deepLinkModal.current).toEqual({ modal: 'condition', id: 7 });
  });

  it('renders PersonaAvatar for each combatant', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 1, character_name: 'Aerande' })],
      [makeOpponent({ id: 10, name: 'Knight' })]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const avatars = screen.getAllByTestId('persona-avatar');
    expect(avatars.length).toBeGreaterThanOrEqual(2);
  });
});
