/**
 * Tests for DeepLinkModalHost — the single Redux-driven host that renders the
 * deep-link modal for all 5 DeepLinkKind values (#551).
 *
 * Setup:
 * - A real Redux store wired with the deepLinkModal reducer (so dispatching
 *   openDeepLink / closeDeepLink drives the host).
 * - A QueryClientProvider whose cache is seeded with a real EncounterDetail via
 *   queryClient.setQueryData(combatKeys.encounter(id), ...) so the cache-reuse
 *   kinds (clash / opponent / participant) resolve without a network fetch.
 * - useConditionInstance is mocked to return a fixture condition.
 */

import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

import { deepLinkModalSlice, openDeepLink } from '@/store/deepLinkModalSlice';
import { combatKeys } from '@/combat/queries';
import { DeepLinkModalHost } from '../DeepLinkModalHost';

// ---------------------------------------------------------------------------
// Mock the condition-instance hook with a fixture
// ---------------------------------------------------------------------------

const conditionFixture = {
  id: 7,
  name: 'Bleeding',
  description: 'Losing blood each round.',
  severity: 3,
  stage_name: 'Deep Wound',
};

vi.mock('@/conditions/queries', () => ({
  useConditionInstance: vi.fn(),
}));

import { useConditionInstance } from '@/conditions/queries';

// ---------------------------------------------------------------------------
// Encounter fixture — seeded into the React Query cache
// ---------------------------------------------------------------------------

const ENCOUNTER_ID = 99;

const clashFixture = {
  id: 42,
  flavor: 'CLASH',
  status: 'ACTIVE',
  progress: 5,
  pc_win_threshold: 10,
  npc_win_threshold: -10,
  npc_opponent: 3,
  contributors: [],
  side_favored: 'PC',
};

const opponentFixture = {
  id: 3,
  name: 'Bandit Captain',
  tier: 'elite',
  health: 8,
  max_health: 12,
};

const participantFixture = {
  id: 5,
  character_name: 'Alaric',
  status: 'active',
  character_status: 'Wounded',
  health: 6,
  max_health: 10,
};

const encounterFixture = {
  id: ENCOUNTER_ID,
  clashes: [clashFixture],
  opponents: [opponentFixture],
  participants: [participantFixture],
};

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

function makeStore() {
  return configureStore({
    reducer: { deepLinkModal: deepLinkModalSlice.reducer },
  });
}

function renderHost() {
  const store = makeStore();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // Seed the encounter cache so cache-reuse kinds resolve.
  queryClient.setQueryData(combatKeys.encounter(ENCOUNTER_ID), encounterFixture);

  const wrapper = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </Provider>
  );

  const utils = render(<DeepLinkModalHost encounterId={ENCOUNTER_ID} />, { wrapper });
  return { store, queryClient, ...utils };
}

beforeEach(() => {
  vi.mocked(useConditionInstance).mockReturnValue({
    data: conditionFixture,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useConditionInstance>);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DeepLinkModalHost', () => {
  it('renders nothing when current is null', () => {
    renderHost();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders the condition modal showing the fixture name on a condition deep link', () => {
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'condition', id: 7 }));
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Bleeding')).toBeInTheDocument();
  });

  it('renders clash detail content on a clash deep link', () => {
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'clash', id: 42 }));
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    // Clash card presentation is reused — its testid is keyed by clash id.
    expect(screen.getByTestId('clash-card-42')).toBeInTheDocument();
  });

  it('renders opponent detail on an opponent deep link', () => {
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'opponent', id: 3 }));
    });
    expect(screen.getByText('Bandit Captain')).toBeInTheDocument();
  });

  it('renders participant detail on a participant deep link', () => {
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'participant', id: 5 }));
    });
    expect(screen.getByText('Alaric')).toBeInTheDocument();
  });

  it('renders a minimal combo fallback dialog on a combo deep link', () => {
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'combo', id: 12 }));
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Combo #12/)).toBeInTheDocument();
  });

  it('dispatches closeDeepLink when the dialog is closed', async () => {
    const user = userEvent.setup();
    const { store } = renderHost();
    act(() => {
      store.dispatch(openDeepLink({ modal: 'condition', id: 7 }));
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Radix renders a labeled close button inside DialogContent.
    await user.click(screen.getByRole('button', { name: /close/i }));

    expect(store.getState().deepLinkModal.current).toBeNull();
  });
});
