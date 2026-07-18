/**
 * Tests for BattleMapCanvas (#2423 finding 7) — place nodes must be present
 * on FIRST render. The original implementation seeded `useNodesState([])`
 * and mirrored `computedNodes` in via a post-render `useEffect`, so the very
 * first commit showed an empty React Flow canvas until that passive effect
 * flushed.
 *
 * `@/map-canvas/MapCanvasShell` is mocked to a trivial stub that renders the
 * `nodes` prop directly — this isolates BattleMapCanvas's own render/effect
 * behavior from React Flow's internal Zustand-store sync (itself driven by a
 * `useLayoutEffect` in `@xyflow/react`'s `StoreUpdater`, which every
 * consumer of the shell — old or new — needs regardless of this fix, and
 * which `@testing-library/react`'s `act()`-wrapped `render()` would flush
 * away either way). What's actually under test here is whether
 * BattleMapCanvas hands the shell populated nodes on mount, or seeds it
 * empty and corrects itself a render later.
 */

import { act } from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { Node } from '@xyflow/react';

import { BattleMapCanvas } from '../BattleMapCanvas';
import type { BattleDetail } from '../../types';

vi.mock('@/map-canvas/MapCanvasShell', () => ({
  MapCanvasShell: ({
    testId,
    nodes,
    emptyState,
  }: {
    testId: string;
    nodes: Node[];
    emptyState?: React.ReactNode;
  }) => {
    if (emptyState) {
      return <>{emptyState}</>;
    }
    return (
      <div data-testid={testId}>
        {nodes.map((node) => (
          <div key={node.id} data-testid="battle-place-node" data-place-id={node.id} />
        ))}
      </div>
    );
  },
}));

const MOCK_DETAIL: BattleDetail = {
  id: 42,
  name: 'Siege of the Gate',
  outcome: null,
  risk_level: 'high',
  is_paused: false,
  round: null,
  sides: [
    {
      id: 1,
      role: 'attacker',
      victory_points: 8,
      victory_threshold: 10,
      posture: 'aggressive',
      covenant_id: 1,
      covenant_name: 'Iron Vanguard',
    },
  ],
  places: [
    {
      id: 1,
      name: 'The Ford',
      terrain_type: 'flooded',
      movement_cost: 2,
      x: 10.5,
      y: -3.0,
      footprint_radius: 2.0,
      controlled_by_id: 1,
      encounter_scene_id: null,
      encounter_roster: null,
      vehicle: null,
      fortifications: [],
    },
    {
      id: 2,
      name: 'The Bridge',
      terrain_type: 'open',
      movement_cost: 1,
      x: -5.0,
      y: 4.0,
      footprint_radius: 1.5,
      controlled_by_id: null,
      encounter_scene_id: null,
      encounter_roster: null,
      vehicle: null,
      fortifications: [],
    },
  ],
  units: [],
  participants: [],
} as unknown as BattleDetail;

describe('BattleMapCanvas', () => {
  it('renders place nodes synchronously on first render (no effect flush)', () => {
    // `@testing-library/react`'s `render()` wraps the mount in `act()`,
    // which drains ALL pending effects (layout AND passive) to a stable
    // fixed point before returning — that would flush away the exact bug
    // this test guards against (nodes seeded empty, corrected a render
    // later by a passive `useEffect`). `flushSync` forces the initial commit
    // to happen synchronously (so we can read the DOM immediately) without
    // draining the passive-effect queue the way `act()` does — so reading
    // the DOM right after `flushSync` returns reflects the true first
    // commit, before any `useEffect` has had a chance to run.
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    flushSync(() => {
      root.render(
        <BattleMapCanvas detail={MOCK_DETAIL} selectedPlaceId={null} onSelectPlace={vi.fn()} />
      );
    });

    const renderedNodeCount = container.querySelectorAll(
      '[data-testid="battle-place-node"]'
    ).length;

    // Flush/unmount inside act() so no pending effect leaks a warning (or a
    // state update) into a later test.
    act(() => {
      root.unmount();
    });
    document.body.removeChild(container);

    expect(renderedNodeCount).toBe(MOCK_DETAIL.places.length);
  });

  it('renders the empty state when there are no places', () => {
    render(
      <BattleMapCanvas
        detail={{ ...MOCK_DETAIL, places: [] }}
        selectedPlaceId={null}
        onSelectPlace={vi.fn()}
      />
    );

    expect(screen.getByTestId('battle-map-canvas-empty')).toBeInTheDocument();
  });
});
