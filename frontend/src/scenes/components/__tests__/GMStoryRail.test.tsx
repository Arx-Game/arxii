/**
 * Tests for GMStoryRail (#3434) - the GM story rail rendered beside the scene.
 *
 * Mocks:
 * - @/gm-adjudication/useActiveCharacterId - resolves the acting GM's own character
 * - @/combat/queries (useDispatchPlayerAction) - the gm_list_conditions and
 *   #3567 advance_clock dispatches
 * - sonner (toast) - the advance-clock success/failure feedback
 * - @/vitals/vitalsQueries (useCharacterVitalsQuery) - per-participant vitals
 * - ../../queries (useGMStoryRailQuery, useSceneScenarioQuery) - the rail
 *   payload and the #3565 scenario payload
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import type { GMStoryRailPayload, SceneDetail, SceneScenarioPayload } from '../../types';

const mockUseActiveCharacterId = vi.fn(() => 7);
vi.mock('@/gm-adjudication/useActiveCharacterId', () => ({
  useActiveCharacterId: () => mockUseActiveCharacterId(),
}));

const mutateAsync = vi.fn(
  (
    body: DispatchBody
  ): Promise<{ backend: string; deferred: boolean; success?: boolean | null; data?: unknown }> => {
    if (body.ref.registry_key === 'advance_clock') {
      return Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'The clock advances: 2/3.',
        data: { size: 3, filled: 2, filled_now: false },
      });
    }
    return Promise.resolve({
      backend: 'registry',
      deferred: false,
      success: true,
      data: { conditions: [{ id: 1, name: 'Winded', severity: 2 }] },
    });
  }
);
interface DispatchBody {
  ref: { backend: string; registry_key: string };
  kwargs: Record<string, unknown>;
}
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({ mutateAsync, isPending: false })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const useCharacterVitalsQuery = vi.fn();
vi.mock('@/vitals/vitalsQueries', () => ({
  useCharacterVitalsQuery: (characterId: number) => useCharacterVitalsQuery(characterId),
}));

const useGMStoryRailQuery = vi.fn();
const useSceneScenarioQuery = vi.fn();
vi.mock('../../queries', () => ({
  useGMStoryRailQuery: (sceneId: string, enabled: boolean) => useGMStoryRailQuery(sceneId, enabled),
  useSceneScenarioQuery: (sceneId: string, enabled: boolean) =>
    useSceneScenarioQuery(sceneId, enabled),
}));

import { GMStoryRail } from '../GMStoryRail';
import { toast } from 'sonner';

function renderRail(scene: SceneDetail) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return render(<GMStoryRail scene={scene} />, { wrapper: Wrapper });
}

function buildScene(overrides: Partial<SceneDetail> = {}): SceneDetail {
  return {
    id: 5,
    name: 'Test Scene',
    description: '',
    date_started: '2026-08-29T00:00:00Z',
    location: null,
    participants: [],
    is_active: true,
    is_owner: false,
    viewer_can_gm: true,
    positions: [],
    position_adjacency: [],
    persona_positions: [],
    active_round: null,
    position_nodes: [],
    position_edges: [],
    running_beat: { id: 9, risk: 'moderate', clock_size: 0 },
    declared_risk: 'moderate',
    clock: null,
    art_url: null,
    ...overrides,
  };
}

function buildPayloadWithClock(clockSize: number): GMStoryRailPayload {
  const payload = buildPayload();
  return {
    ...payload,
    beat: payload.beat === null ? null : { ...payload.beat, clock_size: clockSize },
  };
}

function buildPayload(overrides: Partial<GMStoryRailPayload> = {}): GMStoryRailPayload {
  return {
    beat: {
      id: 9,
      kind: 'encounter',
      risk: 'moderate',
      outcome: 'unsatisfied',
      predicate_type: 'gm_marked',
      clock_size: 0,
      success_consequences_authored: true,
      failure_consequences_authored: false,
      expired_consequences_authored: false,
      internal_description: 'The ambush springs here.',
      opponent_lines: [],
      staged_templates: [],
      staged_battle: null,
    },
    protected_subjects: [],
    clue_placements: [],
    participants: [{ character_sheet_id: 100, name: 'Aerande' }],
    stakes: [],
    activation: null,
    ...overrides,
  };
}

function buildScenarioPayload(overrides: Partial<SceneScenarioPayload> = {}): SceneScenarioPayload {
  return {
    instance_id: 55,
    is_paused: false,
    viewer_is_participant: false,
    group_beat: null,
    gm: {
      node_key: 'ambush',
      flavor_text: '',
      conflict_mode: 'group_vote',
      phase: 'vote',
      is_paused: false,
      ballots: [
        {
          character_id: 100,
          character_name: 'Aerande',
          picked_option_id: 1,
          voted_option_id: null,
        },
      ],
      last_deed: { option_key: 'fight', outcome_name: 'success' },
      beat_outcome: 'satisfied',
      beat_outcome_key: 'satisfied',
    },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useCharacterVitalsQuery.mockReturnValue({
    data: { health: 40, max_health: 50, health_percentage: 0.8, status: 'alive' },
  });
  useSceneScenarioQuery.mockReturnValue({ data: undefined });
});

describe('GMStoryRail', () => {
  it('renders nothing when the viewer cannot GM the scene', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    const { container } = renderRail(buildScene({ viewer_can_gm: false }));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the "no beat running" fallback when the GM has no running beat', () => {
    useGMStoryRailQuery.mockReturnValue({ data: undefined });
    renderRail(buildScene({ running_beat: null }));
    expect(screen.getByTestId('gm-story-rail-no-beat')).toHaveTextContent(
      'No beat running - Run one from the panel.'
    );
  });

  it('renders the beat summary section for a qualifying GM', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    renderRail(buildScene());
    const beatSection = screen.getByTestId('gm-story-rail-beat');
    expect(beatSection).toHaveTextContent('encounter');
    expect(beatSection).toHaveTextContent('moderate');
    expect(screen.getByTestId('gm-story-rail-internal-description')).toHaveTextContent(
      'The ambush springs here.'
    );
  });

  it('renders nothing when the server denies the rail (below JUNIOR trust)', () => {
    useGMStoryRailQuery.mockReturnValue({ data: null });
    const { container } = renderRail(buildScene());
    expect(container).toBeEmptyDOMElement();
  });

  it('dispatches gm_list_conditions per participant and renders the result', async () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    renderRail(buildScene());

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'gm_list_conditions' },
        kwargs: { target: 100 },
      })
    );
    expect(await screen.findByTestId('gm-rail-participant-conditions')).toHaveTextContent(
      'Winded (severity 2)'
    );
  });

  it('a denied vitals fetch on one participant does not break the rail', () => {
    useCharacterVitalsQuery.mockReturnValue({ data: null });
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayload({
        participants: [
          { character_sheet_id: 100, name: 'Aerande' },
          { character_sheet_id: 101, name: 'Bellamy' },
        ],
      }),
    });
    renderRail(buildScene());

    // Both participant rows still render even though neither has vitals.
    expect(screen.getByTestId('gm-rail-participant-100')).toHaveTextContent('Aerande');
    expect(screen.getByTestId('gm-rail-participant-100')).toHaveTextContent('Vitals unavailable.');
    expect(screen.getByTestId('gm-rail-participant-101')).toHaveTextContent('Bellamy');
  });

  it('renders protected subjects and clue placements when served', () => {
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayload({
        protected_subjects: [
          {
            id: 1,
            story: 2,
            subject_kind: 'npc_fate',
            subject_sheet: 3,
            subject_item: null,
            subject_society: null,
            subject_organization: null,
            subject_label: null,
            beat: null,
            is_active: true,
            notes: '',
            created_at: '2026-08-29T00:00:00Z',
          },
        ],
        clue_placements: [
          { id: 5, clue_name: 'Torn Letter', detect_difficulty: 10, is_active: true },
        ],
      }),
    });
    renderRail(buildScene());
    expect(screen.getByTestId('gm-story-rail-protected-subjects')).toHaveTextContent('npc_fate');
    expect(screen.getByTestId('gm-story-rail-clue-placements')).toHaveTextContent('Torn Letter');
  });

  it('renders the Stakes section with severity labels, activation, and a resolved outcome', () => {
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayload({
        stakes: [
          {
            id: 11,
            player_summary: 'A dueling scar, worn for all to see.',
            severity: 4,
            subject_kind: 'personal_jeopardy',
            outcome: { column: 'loss', outcome_key: '', resolution_summary: 'It goes badly.' },
          },
          {
            id: 12,
            player_summary: 'Standing with the merchant guild.',
            severity: 1,
            subject_kind: 'faction',
            outcome: null,
          },
        ],
        activation: { locked_at: '2026-09-02T19:51:39Z', effective_risk: 'high', is_ready: true },
      }),
    });
    renderRail(buildScene());

    const section = screen.getByTestId('gm-story-rail-stakes');
    expect(section).toHaveTextContent('Stakes');
    expect(screen.getByTestId('gm-story-rail-activation')).toHaveTextContent('high');
    expect(screen.getByTestId('gm-story-rail-activation')).toHaveTextContent('ready');

    const firstStake = screen.getByTestId('gm-story-rail-stake-11');
    expect(firstStake).toHaveTextContent('A dueling scar, worn for all to see.');
    expect(firstStake).toHaveTextContent('Dire');
    expect(firstStake).toHaveTextContent('personal_jeopardy');
    expect(screen.getByTestId('gm-story-rail-stake-outcome-11')).toHaveTextContent('Loss');
    expect(screen.getByTestId('gm-story-rail-stake-outcome-11')).toHaveTextContent(
      'It goes badly.'
    );

    const secondStake = screen.getByTestId('gm-story-rail-stake-12');
    expect(secondStake).toHaveTextContent('Standing with the merchant guild.');
    expect(secondStake).toHaveTextContent('Setback');
    expect(screen.queryByTestId('gm-story-rail-stake-outcome-12')).not.toBeInTheDocument();
  });

  it('renders no Stakes section when there are no stakes and no activation', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    renderRail(buildScene());
    expect(screen.queryByTestId('gm-story-rail-stakes')).not.toBeInTheDocument();
  });

  it('renders the Scenario section with ballots and the last deed when gm is present', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    useSceneScenarioQuery.mockReturnValue({ data: buildScenarioPayload() });
    renderRail(buildScene());
    const section = screen.getByTestId('gm-story-rail-scenario');
    expect(section).toHaveTextContent('ambush');
    expect(section).toHaveTextContent('vote');
    expect(screen.getByTestId('gm-story-rail-scenario-ballots')).toHaveTextContent(
      'Aerande: picked, no vote'
    );
    expect(screen.getByTestId('gm-story-rail-scenario-last-deed')).toHaveTextContent(
      'fight: success'
    );
    expect(screen.getByTestId('gm-story-rail-scenario-outcome')).toHaveTextContent('satisfied');
  });

  it('renders no Scenario section when the scenario query has no gm view', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    useSceneScenarioQuery.mockReturnValue({ data: buildScenarioPayload({ gm: null }) });
    renderRail(buildScene());
    expect(screen.queryByTestId('gm-story-rail-scenario')).not.toBeInTheDocument();
  });
});

describe('GMStoryRail scene clock (#3567)', () => {
  it('renders no clock line when the running beat carries no clock', () => {
    useGMStoryRailQuery.mockReturnValue({ data: buildPayload() });
    renderRail(buildScene());
    expect(screen.queryByTestId('gm-story-rail-clock')).not.toBeInTheDocument();
  });

  it('reads the clock line from scene.clock and lets the GM advance it', async () => {
    const user = userEvent.setup();
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayloadWithClock(3),
    });
    renderRail(buildScene({ clock: { size: 3, filled: 1 } }));

    const clockLine = screen.getByTestId('gm-story-rail-clock');
    expect(clockLine).toHaveTextContent('1/3');

    await user.click(screen.getByTestId('gm-story-rail-advance-clock'));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'advance_clock' },
        kwargs: { by: 1 },
      })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('The clock advances: 2/3.'));
  });

  it('renders no Advance button once the clock is full', () => {
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayloadWithClock(3),
    });
    renderRail(buildScene({ clock: { size: 3, filled: 3 } }));

    const clockLine = screen.getByTestId('gm-story-rail-clock');
    expect(clockLine).toHaveTextContent('3/3');
    expect(screen.queryByTestId('gm-story-rail-advance-clock')).not.toBeInTheDocument();
  });

  it('renders the beat clock_size as the fallback 0/N count before scene.clock is available', () => {
    useGMStoryRailQuery.mockReturnValue({
      data: buildPayloadWithClock(4),
    });
    renderRail(buildScene({ clock: null }));

    expect(screen.getByTestId('gm-story-rail-clock')).toHaveTextContent('0/4');
    expect(screen.queryByTestId('gm-story-rail-advance-clock')).not.toBeInTheDocument();
  });
});
