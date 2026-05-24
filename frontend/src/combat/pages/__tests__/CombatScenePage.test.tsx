/**
 * Tests for CombatScenePage — Phase 11.
 *
 * Smoke tests: renders header + left column + right column.
 * Empty state when no active encounter for the scene.
 * Mounts CombatTurnPanel with the resolved encounter id.
 *
 * Mocks:
 * - react-router-dom (useParams → { id: '42' })
 * - @/combat/queries (useEncounterForScene, useCombatEncounter, useAvailableActions, ...)
 * - @/scenes/queries (fetchScene)
 * - @/roster/queries (useMyRosterEntriesQuery)
 * - @/store/hooks (useAppSelector)
 * - @/scenes/components/SceneInteractionPanel (stub)
 * - @/scenes/components/PendingActionAttachments (stub)
 * - @/game/components/CommandInput (stub)
 * - @/combat/CombatTurnPanel (stub — isolates layout smoke tests)
 * - @/scenes/hooks/usePendingUnlinkedActions (stub)
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks — hoisted before imports
// ---------------------------------------------------------------------------

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: vi.fn().mockReturnValue({ id: '42' }),
  };
});

vi.mock('@/combat/queries', () => ({
  useEncounterForScene: vi.fn(),
  useCombatEncounter: vi.fn(),
  useAvailableActions: vi.fn().mockReturnValue({ data: [], isLoading: false, isError: false }),
  useAvailableCombos: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useUpgradeCombo: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
  useDispatchPlayerAction: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  combatKeys: {
    all: ['combat'],
    encounter: (id: number) => ['combat', 'encounter', id],
    encountersForScene: (id: number) => ['combat', 'encounters-for-scene', id],
    combos: (id: number) => ['combat', 'combos', id],
    availableActions: (id: number) => ['combat', 'available-actions', id],
  },
}));

vi.mock('@/scenes/queries', () => ({
  fetchScene: vi.fn().mockResolvedValue({
    id: 42,
    name: 'Test Scene',
    description: 'A test scene',
    is_active: true,
    is_owner: false,
  }),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn().mockReturnValue({
    data: [
      {
        id: 1,
        name: 'Aerande',
        character_id: 10,
        primary_persona_id: 99,
        profile_picture_url: null,
      },
    ],
  }),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn().mockReturnValue('Aerande'),
  useAccount: vi.fn().mockReturnValue({ id: 1, username: 'player1' }),
}));

// Stub SceneInteractionPanel — renders a minimal stand-in
vi.mock('@/scenes/components/SceneInteractionPanel', () => ({
  SceneInteractionPanel: ({ sceneId }: { sceneId: string }) => (
    <div data-testid="scene-interaction-panel-stub">SceneInteractionPanel [{sceneId}]</div>
  ),
}));

// Stub PendingActionAttachments
vi.mock('@/scenes/components/PendingActionAttachments', () => ({
  PendingActionAttachments: () => (
    <div data-testid="pending-action-attachments-stub" />
  ),
}));

// Stub CommandInput
vi.mock('@/game/components/CommandInput', () => ({
  CommandInput: () => <div data-testid="command-input-stub" />,
}));

// Stub CombatTurnPanel — exposes encounterId so we can assert it
vi.mock('@/combat/CombatTurnPanel', () => ({
  CombatTurnPanel: ({
    encounterId,
    characterId,
    characterSheetId,
  }: {
    encounterId: number;
    characterId: number;
    characterSheetId: number;
  }) => (
    <div
      data-testid="combat-turn-panel-stub"
      data-encounter-id={encounterId}
      data-character-id={characterId}
      data-character-sheet-id={characterSheetId}
    >
      CombatTurnPanel [{encounterId}]
    </div>
  ),
}));

// Stub usePendingUnlinkedActions
vi.mock('@/scenes/hooks/usePendingUnlinkedActions', () => ({
  usePendingUnlinkedActions: vi.fn().mockReturnValue({ data: [] }),
}));

// Stub SceneHeader — renders scene name so we can assert it
vi.mock('@/scenes/components/SceneHeader', () => ({
  SceneHeader: ({ scene }: { scene?: { name?: string } }) => (
    <div data-testid="scene-header-stub">{scene?.name ?? 'Loading…'}</div>
  ),
}));

// Stub actionQueries to prevent fetch noise
vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn().mockResolvedValue({ results: [] }),
  createActionRequest: vi.fn().mockResolvedValue({}),
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import * as combatQueries from '@/combat/queries';
import { CombatScenePage } from '../CombatScenePage';

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

const mockedUseEncounterForScene =
  combatQueries.useEncounterForScene as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  // Default: one active encounter in the scene
  mockedUseEncounterForScene.mockReturnValue({
    data: { id: 7, scene: 42, status: 'declaring', round_number: 1, participant_count: 2, opponent_count: 0 },
    isLoading: false,
    isError: false,
  });
  (combatQueries.useCombatEncounter as ReturnType<typeof vi.fn>).mockReturnValue({
    data: {
      id: 7,
      round_number: 1,
      is_participant: true,
      is_gm: false,
      participants: [],
      opponents: [],
      current_round_actions: [],
      clashes: [],
      created_at: '2026-05-24T00:00:00Z',
    },
    isLoading: false,
    isError: false,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CombatScenePage — smoke render', () => {
  it('renders the scene header', () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('scene-header-stub')).toBeInTheDocument();
  });

  it('renders the left column with the interaction panel', () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('scene-interaction-panel-stub')).toBeInTheDocument();
    expect(screen.getByTestId('scene-interaction-panel-stub')).toHaveTextContent(
      'SceneInteractionPanel [42]'
    );
  });

  it('renders the right column', () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('combat-scene-right')).toBeInTheDocument();
  });

  it('mounts CombatTurnPanel with the resolved encounter id', () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    const panel = screen.getByTestId('combat-turn-panel-stub');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute('data-encounter-id', '7');
  });

  it('passes characterId and characterSheetId from the active roster entry', () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    const panel = screen.getByTestId('combat-turn-panel-stub');
    expect(panel).toHaveAttribute('data-character-id', '10');
    expect(panel).toHaveAttribute('data-character-sheet-id', '10');
  });

  it('renders the composer when scene is active and character is resolved', async () => {
    render(<CombatScenePage />, { wrapper: createWrapper() });
    // Wait for the scene fetch to resolve (is_active: true) so the composer renders
    await waitFor(() => {
      expect(screen.getByTestId('combat-scene-composer')).toBeInTheDocument();
    });
    expect(screen.getByTestId('command-input-stub')).toBeInTheDocument();
  });
});

describe('CombatScenePage — empty state', () => {
  it('renders "No active combat" when there is no encounter for the scene', () => {
    mockedUseEncounterForScene.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });

    render(<CombatScenePage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combat-no-encounter')).toBeInTheDocument();
    expect(screen.getByText(/no active combat/i)).toBeInTheDocument();
    expect(screen.queryByTestId('combat-turn-panel-stub')).not.toBeInTheDocument();
  });

  it('renders a loading indicator while encounter is loading', () => {
    mockedUseEncounterForScene.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    render(<CombatScenePage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combat-encounter-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('combat-turn-panel-stub')).not.toBeInTheDocument();
  });
});
