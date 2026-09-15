/**
 * Tests for ScenarioCard (#3565) - the mission scenario card on the scene page.
 *
 * Mocks:
 * - ../../queries (useSceneScenarioQuery) - the scenario payload itself
 * - @/missions/components/GroupBeatCard - stubbed to a marker so this test
 *   doesn't need to reproduce the group-beat card's own fetching/polling.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { SceneDetail, SceneScenarioPayload } from '../../types';

const useSceneScenarioQuery = vi.fn();
vi.mock('../../queries', () => ({
  useSceneScenarioQuery: (sceneId: string, enabled: boolean) =>
    useSceneScenarioQuery(sceneId, enabled),
}));

vi.mock('@/missions/components/GroupBeatCard', () => ({
  GroupBeatCard: ({ instanceId, roomKey }: { instanceId: number; roomKey: string }) => (
    <div data-testid="group-beat-card-stub">
      instance:{instanceId} room:{roomKey}
    </div>
  ),
}));

import { ScenarioCard } from '../ScenarioCard';

function buildScene(overrides: Partial<SceneDetail> = {}): SceneDetail {
  return {
    id: 7,
    name: 'Test Scene',
    description: '',
    date_started: '2026-09-01T00:00:00Z',
    location: null,
    participants: [],
    is_active: true,
    is_owner: false,
    viewer_can_gm: false,
    positions: [],
    position_adjacency: [],
    persona_positions: [],
    active_round: null,
    position_nodes: [],
    position_edges: [],
    running_beat: null,
    declared_risk: null,
    clock: null,
    art_url: null,
    ...overrides,
  };
}

function buildPayload(overrides: Partial<SceneScenarioPayload> = {}): SceneScenarioPayload {
  return {
    instance_id: 55,
    is_paused: false,
    viewer_is_participant: true,
    group_beat: null,
    gm: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ScenarioCard', () => {
  it('renders nothing when there is no running scenario instance', () => {
    useSceneScenarioQuery.mockReturnValue({ data: buildPayload({ instance_id: null }) });
    const { container } = render(<ScenarioCard scene={buildScene()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the viewer is not a participant', () => {
    useSceneScenarioQuery.mockReturnValue({
      data: buildPayload({ viewer_is_participant: false }),
    });
    const { container } = render(<ScenarioCard scene={buildScene()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the query returns null (denied or no scene)', () => {
    useSceneScenarioQuery.mockReturnValue({ data: null });
    const { container } = render(<ScenarioCard scene={buildScene()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the paused notice while a fight has the scenario paused', () => {
    useSceneScenarioQuery.mockReturnValue({ data: buildPayload({ is_paused: true }) });
    render(<ScenarioCard scene={buildScene()} />);
    expect(screen.getByTestId('scenario-card-paused')).toHaveTextContent(
      'A fight is underway; the scenario continues when it ends.'
    );
  });

  it('renders GroupBeatCard with the running instance for a participant', () => {
    useSceneScenarioQuery.mockReturnValue({ data: buildPayload({ instance_id: 55 }) });
    render(<ScenarioCard scene={buildScene({ id: 7 })} />);
    expect(screen.getByTestId('group-beat-card-stub')).toHaveTextContent(
      'instance:55 room:scene-7'
    );
  });
});
