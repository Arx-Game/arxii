/**
 * CombatGMTab (#3557): the rail's GM tab body. Encounter controls render only
 * once the encounter query has data (never the "Start Encounter" card inside a
 * tab whose premise is a live encounter); the GM tools render with exactly the
 * combat tab set.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockUseCombatEncounter = vi.fn();
const mockOpenStandoff = vi.fn();
vi.mock('@/combat/queries', () => ({
  useCombatEncounter: () => mockUseCombatEncounter(),
  useOpenStandoff: () => ({ mutate: mockOpenStandoff, isPending: false, error: null }),
  useStandoffMorale: () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() }),
}));

vi.mock('@/combat/sections/GMEncounterControls', () => ({
  GMEncounterControls: ({
    sceneId,
    encounter,
    viewerCanGm,
  }: {
    sceneId: number;
    encounter: { id: number } | null;
    viewerCanGm: boolean;
  }) => (
    <div
      data-testid="gm-encounter-controls-stub"
      data-scene-id={sceneId}
      data-encounter-id={encounter?.id ?? 'none'}
      data-viewer-can-gm={String(viewerCanGm)}
    />
  ),
}));

vi.mock('@/scenes/components/GMAdjudicationPanel', () => ({
  COMBAT_GM_TOOL_TABS: ['condition', 'dramaticbeat', 'traps'],
  GMAdjudicationPanel: ({ tabs, title }: { tabs?: readonly string[]; title?: string }) => (
    <div
      data-testid="gm-adjudication-panel-stub"
      data-tabs={(tabs ?? []).join(',')}
      data-title={title}
    />
  ),
}));

import { CombatGMTab } from '../CombatGMTab';
import type { SceneDetail } from '@/scenes/types';

const scene = { id: 1, viewer_can_gm: true, personas: [] } as unknown as SceneDetail;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CombatGMTab', () => {
  it('renders the GM tools with the combat tab set and a rail title', () => {
    mockUseCombatEncounter.mockReturnValue({ data: undefined });
    render(<CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />);
    const panel = screen.getByTestId('gm-adjudication-panel-stub');
    expect(panel).toHaveAttribute('data-tabs', 'condition,dramaticbeat,traps');
    expect(panel).toHaveAttribute('data-title', 'Fight Tools');
  });

  it('withholds the encounter controls until the encounter query has data', () => {
    mockUseCombatEncounter.mockReturnValue({ data: undefined });
    render(<CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />);
    expect(screen.queryByTestId('gm-encounter-controls-stub')).not.toBeInTheDocument();
  });

  it('mounts the encounter controls with the loaded encounter', () => {
    mockUseCombatEncounter.mockReturnValue({ data: { id: 7, is_gm: true } });
    render(<CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />);
    const controls = screen.getByTestId('gm-encounter-controls-stub');
    expect(controls).toHaveAttribute('data-encounter-id', '7');
    expect(controls).toHaveAttribute('data-scene-id', '1');
    expect(controls).toHaveAttribute('data-viewer-can-gm', 'true');
  });

  it('offers Open a standoff at round zero when no standoff is open', async () => {
    mockUseCombatEncounter.mockReturnValue({
      data: { id: 7, is_gm: true, round_number: 0, gm_standoff: null },
    });
    render(<CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Open a standoff' }));
    expect(mockOpenStandoff).toHaveBeenCalled();
  });

  it('hides Open a standoff after round one and shows the panel when a standoff is open', () => {
    mockUseCombatEncounter.mockReturnValue({
      data: { id: 7, is_gm: true, round_number: 2, gm_standoff: null },
    });
    const { unmount } = render(
      <CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />
    );
    expect(screen.queryByRole('button', { name: 'Open a standoff' })).toBeNull();
    unmount();
    mockUseCombatEncounter.mockReturnValue({
      data: {
        id: 7,
        is_gm: true,
        round_number: 0,
        gm_standoff: { place: 'x', participants: [], groups: [] },
      },
    });
    render(<CombatGMTab sceneId={1} encounterId={7} scene={scene} viewerCanGm />);
    expect(screen.getByTestId('gm-standoff-panel')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open a standoff' })).toBeNull();
  });
});
