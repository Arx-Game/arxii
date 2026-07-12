/**
 * Tests for CombatRail (#2197) — migrated from the deleted CombatScenePage's
 * rail-specific smoke tests (Phase 11).
 *
 * Mocks:
 * - @/roster/queries (useMyRosterEntriesQuery)
 * - @/store/hooks (useAppSelector)
 * - @/combat/CombatTurnPanel (stub — isolates layout smoke tests)
 * - @/combat/components/CombatTacticalMap (stub)
 * - @/combat/modals/DeepLinkModalHost (stub — has its own dedicated test)
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn().mockReturnValue({
    data: [
      {
        id: 1,
        name: 'Aerande',
        character_id: 10,
        primary_persona_id: 99,
        active_persona_id: 99,
        profile_picture_url: null,
      },
    ],
  }),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn().mockReturnValue('Aerande'),
  useAccount: vi.fn().mockReturnValue({ id: 1, username: 'player1' }),
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

// Stub CombatTacticalMap — exposes encounterId/characterId so we can assert them
vi.mock('@/combat/components/CombatTacticalMap', () => ({
  CombatTacticalMap: ({
    encounterId,
    characterId,
  }: {
    encounterId: number;
    characterId: number;
  }) => (
    <div
      data-testid="combat-tactical-map"
      data-encounter-id={encounterId}
      data-character-id={characterId}
    >
      CombatTacticalMap [{encounterId}]
    </div>
  ),
}));

// Stub DeepLinkModalHost — has its own dedicated test; here it would otherwise
// pull in useAppDispatch/useAppSelector against the deepLinkModal slice.
vi.mock('@/combat/modals/DeepLinkModalHost', () => ({
  DeepLinkModalHost: ({ encounterId }: { encounterId: number }) => (
    <div data-testid="deep-link-modal-host-stub" data-encounter-id={encounterId} />
  ),
}));

import { CombatRail } from '../CombatRail';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CombatRail — smoke render', () => {
  it('mounts CombatTurnPanel with the resolved encounter id', () => {
    render(<CombatRail sceneId={42} encounterId={7} />, { wrapper: createWrapper() });
    const panel = screen.getByTestId('combat-turn-panel-stub');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute('data-encounter-id', '7');
  });

  it('defaults the right rail to the "Your Turn" tab', () => {
    render(<CombatRail sceneId={42} encounterId={7} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('combat-turn-panel-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('combat-tactical-map')).not.toBeInTheDocument();
  });

  it('switches to the map tab and renders CombatTacticalMap', async () => {
    const user = userEvent.setup();
    render(<CombatRail sceneId={42} encounterId={7} />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('rail-tab-map'));

    const map = screen.getByTestId('combat-tactical-map');
    expect(map).toBeInTheDocument();
    expect(map).toHaveAttribute('data-encounter-id', '7');
    expect(map).toHaveAttribute('data-character-id', '10');
    expect(screen.queryByTestId('combat-turn-panel-stub')).not.toBeInTheDocument();
  });

  it('passes characterId and characterSheetId from the active roster entry', () => {
    render(<CombatRail sceneId={42} encounterId={7} />, { wrapper: createWrapper() });
    const panel = screen.getByTestId('combat-turn-panel-stub');
    expect(panel).toHaveAttribute('data-character-id', '10');
    expect(panel).toHaveAttribute('data-character-sheet-id', '10');
  });

  it('mounts the deep-link modal host with the resolved encounter id', () => {
    render(<CombatRail sceneId={42} encounterId={7} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('deep-link-modal-host-stub')).toHaveAttribute(
      'data-encounter-id',
      '7'
    );
  });
});

describe('CombatRail — deterministic encounter selection', () => {
  it('forwards exactly the encounter id it is given, not one it re-derives', () => {
    render(<CombatRail sceneId={42} encounterId={99} />, { wrapper: createWrapper() });

    const panel = screen.getByTestId('combat-turn-panel-stub');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute('data-encounter-id', '99');
  });
});
