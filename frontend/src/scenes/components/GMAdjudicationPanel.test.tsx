import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import type { SceneDetail } from '../types';

// Roster + active-character resolution (mirrors PersonaContextMenu.test.tsx)
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'GMChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: null,
        active_persona_id: null,
      },
    ],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'GMChar' }, auth: {} })
  ),
}));

interface DispatchBody {
  ref: { backend: string; registry_key: string };
  kwargs: Record<string, unknown>;
}

const mutateAsync = vi.fn(
  (_body: DispatchBody): Promise<import('@/combat/types').DispatchResult> =>
    Promise.resolve({ backend: 'registry', deferred: false, success: true, message: 'Done.' })
);
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn((_characterId: number) => ({
    mutateAsync,
    isPending: false,
  })),
}));

vi.mock('@/gm-adjudication/queries', () => ({
  useCheckTypeCatalog: vi.fn((_search: string, _enabled: boolean) => ({
    data: [
      {
        id: 7,
        name: 'Power Strike',
        category: 1,
        category_name: 'Combat',
        description: '',
        trait_summary: 'Strength',
      },
    ],
  })),
  useConditionTemplateCatalog: vi.fn((_enabled: boolean) => ({
    data: [{ id: 3, name: 'Winded' }],
  })),
  useSituationTemplateCatalog: vi.fn((_enabled: boolean) => ({
    data: [{ id: 5, name: 'Ambush', category: 1, category_name: 'Combat' }],
  })),
  useChallengeTemplateCatalog: vi.fn((_enabled: boolean) => ({
    data: [{ id: 9, name: 'Locked Gate', category: 1, category_name: 'Exploration' }],
  })),
  useItemTemplateCatalog: vi.fn((_search: string, _enabled: boolean) => ({
    data: [{ id: 21, name: 'Silver Locket' }],
  })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { GMAdjudicationPanel } from './GMAdjudicationPanel';
import { useDispatchPlayerAction } from '@/combat/queries';
import { toast } from 'sonner';

function makeScene(overrides: Partial<SceneDetail> = {}): SceneDetail {
  return {
    id: 1,
    name: 'Test Scene',
    description: '',
    date_started: '2026-01-01T00:00:00Z',
    location: { id: 10, name: 'Room' },
    participants: [],
    is_active: true,
    is_owner: false,
    viewer_can_gm: true,
    personas: [{ id: 100, name: 'Target Persona', persona_type: 'primary', character_sheet: 55 }],
    positions: [],
    position_adjacency: [],
    persona_positions: [],
    active_round: null,
    position_nodes: [],
    position_edges: [],
    running_beat: null,
    ...overrides,
  };
}

beforeEach(() => {
  mutateAsync.mockClear();
  (toast.success as ReturnType<typeof vi.fn>).mockClear();
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
});

test('renders nothing when the viewer cannot GM the scene', () => {
  const { container } = render(<GMAdjudicationPanel scene={makeScene({ viewer_can_gm: false })} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders nothing while scene data has not loaded yet', () => {
  const { container } = render(<GMAdjudicationPanel scene={undefined} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders the panel with all four tabs when the viewer can GM', () => {
  render(<GMAdjudicationPanel scene={makeScene()} />);
  expect(screen.getByTestId('gm-adjudication-panel')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-check')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-award')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-condition')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-situation')).toBeInTheDocument();
});

test('Call Check tab dispatches gm_invoke_check with the picked target and check', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.selectOptions(screen.getByTestId('gm-check-type-select'), '7');
  await user.click(screen.getByTestId('gm-check-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_invoke_check' },
    kwargs: { target: 55, check_type_ref: 7, difficulty: 'normal' },
  });
});

test('Award tab dispatches gm_award_progression with the xp payload', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-award'));
  await user.type(screen.getByLabelText('Amount'), '10');
  await user.click(screen.getByTestId('gm-award-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_award_progression' },
    kwargs: { target: 55, award_type: 'xp', description: undefined, amount: 10 },
  });
});

test('Condition tab dispatches gm_apply_condition with the condition name', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-condition'));
  await user.selectOptions(screen.getByTestId('gm-condition-select'), 'Winded');
  await user.click(screen.getByTestId('gm-condition-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_apply_condition' },
    kwargs: { target: 55, condition_ref: 'Winded', note: undefined },
  });
});

test('Quick Edge button dispatches gm_apply_condition with condition_ref Edge (#3387)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-condition'));
  await user.click(screen.getByTestId('gm-condition-quick-edge'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_apply_condition' },
    kwargs: { target: 55, condition_ref: 'Edge' },
  });
});

test('Quick Setback button dispatches gm_apply_condition with condition_ref Setback (#3387)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-condition'));
  await user.click(screen.getByTestId('gm-condition-quick-setback'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_apply_condition' },
    kwargs: { target: 55, condition_ref: 'Setback' },
  });
});

test('Quick Edge button is disabled with no target selected', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);
  await user.click(screen.getByTestId('gm-tab-condition'));
  expect(screen.getByTestId('gm-condition-quick-edge')).toBeDisabled();
});

test('Dramatic Beat tab dispatches gm_trigger_dramatic_beat with target + reason (#3387)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-dramaticbeat'));
  await user.type(screen.getByTestId('gm-dramaticbeat-reason'), 'a costly misstep');
  await user.click(screen.getByTestId('gm-dramaticbeat-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'gm_trigger_dramatic_beat' },
    kwargs: { target: 55, reason: 'a costly misstep' },
  });
});

test('Dramatic Beat tab submit is disabled without a reason', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-dramaticbeat'));

  expect(screen.getByTestId('gm-dramaticbeat-submit')).toBeDisabled();
});

test('Situation tab dispatches set_situation with no target kwarg', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.click(screen.getByTestId('gm-tab-situation'));
  await user.selectOptions(screen.getByTestId('gm-situation-select'), '5');
  await user.click(screen.getByTestId('gm-situation-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'set_situation' },
    kwargs: { situation_template_id: 5 },
  });
});

test('Situation tab in Challenge mode dispatches place_challenge with target_object_name', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.click(screen.getByTestId('gm-tab-situation'));
  await user.selectOptions(screen.getByLabelText('Placement kind'), 'challenge');
  await user.selectOptions(screen.getByTestId('gm-challenge-select'), '9');
  await user.type(screen.getByLabelText('What embodies it'), 'the barred gate');
  await user.click(screen.getByTestId('gm-situation-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'place_challenge' },
    kwargs: { challenge_template_id: 9, target_object_name: 'the barred gate' },
  });
});

test('a failed dispatch surfaces the refusal message via toast.error', async () => {
  mutateAsync.mockResolvedValueOnce({
    backend: 'registry',
    deferred: false,
    success: false,
    message: 'You must hold Senior GM trust or higher.',
  });
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.selectOptions(screen.getByTestId('gm-check-type-select'), '7');
  await user.click(screen.getByTestId('gm-check-submit'));

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith('You must hold Senior GM trust or higher.')
  );
});

test('useDispatchPlayerAction is called with the resolved active character id', () => {
  render(<GMAdjudicationPanel scene={makeScene()} />);
  expect(useDispatchPlayerAction).toHaveBeenCalledWith(42);
});

// ---------------------------------------------------------------------------
// #3431 — Grant Item, Stage, Traps tabs + Condition tab Remove mode.
// ---------------------------------------------------------------------------

test('renders the three new #3431 tabs', () => {
  render(<GMAdjudicationPanel scene={makeScene()} />);
  expect(screen.getByTestId('gm-tab-grantitem')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-stage')).toBeInTheDocument();
  expect(screen.getByTestId('gm-tab-traps')).toBeInTheDocument();
});

test('Grant Item tab dispatches grant_item with the target persona name (#3431)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-grantitem'));
  await user.selectOptions(screen.getByTestId('gm-grantitem-template-select'), 'Silver Locket');
  await user.click(screen.getByTestId('gm-grantitem-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'grant_item' },
    kwargs: {
      target_name: 'Target Persona',
      template_name: 'Silver Locket',
    },
  });
});

test('Stage tab in Prop mode dispatches stage_prop with item_template (#3431)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.click(screen.getByTestId('gm-tab-stage'));
  await user.selectOptions(screen.getByTestId('gm-stage-template-select'), 'Silver Locket');
  await user.click(screen.getByTestId('gm-stage-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'stage_prop' },
    kwargs: { item_template: 'Silver Locket' },
  });
});

test('Stage tab in Property mode dispatches stage_property with target_id (#3431)', async () => {
  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-stage'));
  await user.selectOptions(screen.getByTestId('gm-stage-mode-select'), 'property');
  await user.type(screen.getByTestId('gm-stage-property-name'), 'dark');
  await user.click(screen.getByTestId('gm-stage-submit'));

  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  expect(mutateAsync).toHaveBeenCalledWith({
    ref: { backend: 'registry', registry_key: 'stage_property' },
    kwargs: { property: 'dark', target_id: 55 },
  });
});

test('Traps tab lists traps on open, and Arm dispatches + refreshes the list (#3431)', async () => {
  mutateAsync
    .mockResolvedValueOnce({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'listed',
      data: { traps: [{ id: 5, name: 'Pit Trap', is_armed: false, position: 'Doorway' }] },
    })
    .mockResolvedValueOnce({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'You arm Pit Trap.',
    })
    .mockResolvedValueOnce({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'listed',
      data: { traps: [{ id: 5, name: 'Pit Trap', is_armed: true, position: 'Doorway' }] },
    });

  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);
  await user.click(screen.getByTestId('gm-tab-traps'));

  await waitFor(() => expect(screen.getByTestId('gm-trap-row-5')).toBeInTheDocument());
  expect(mutateAsync).toHaveBeenNthCalledWith(1, {
    ref: { backend: 'registry', registry_key: 'list_room_traps' },
    kwargs: {},
  });

  await user.click(screen.getByTestId('gm-trap-arm-5'));

  await waitFor(() =>
    expect(mutateAsync).toHaveBeenNthCalledWith(2, {
      ref: { backend: 'registry', registry_key: 'arm_trap' },
      kwargs: { trap_id: 5 },
    })
  );
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
  expect(mutateAsync).toHaveBeenNthCalledWith(3, {
    ref: { backend: 'registry', registry_key: 'list_room_traps' },
    kwargs: {},
  });
});

// ---------------------------------------------------------------------------
// #3425 — Run Beat tab: session prep on story beats.
// ---------------------------------------------------------------------------

test('renders the Run Beat tab', () => {
  render(<GMAdjudicationPanel scene={makeScene()} />);
  expect(screen.getByTestId('gm-tab-runbeat')).toBeInTheDocument();
});

test('Run Beat tab lists runnable beats on open, and Run dispatches run_beat (#3425)', async () => {
  mutateAsync
    .mockResolvedValueOnce({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'listed',
      data: {
        beats: [
          {
            id: 12,
            story_title: 'The Long Watch',
            episode_title: 'Ambush at Dusk',
            kind: 'encounter',
            risk: 'high',
            opponent_line_count: 2,
            staged_template_count: 0,
          },
        ],
      },
    })
    .mockResolvedValueOnce({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Beat #12 is now running in this scene.',
    });

  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);
  await user.click(screen.getByTestId('gm-tab-runbeat'));

  await waitFor(() => expect(screen.getByTestId('gm-runbeat-row-12')).toBeInTheDocument());
  expect(mutateAsync).toHaveBeenNthCalledWith(1, {
    ref: { backend: 'registry', registry_key: 'gm_list_runnable_beats' },
    kwargs: {},
  });

  await user.click(screen.getByTestId('gm-runbeat-run-12'));

  await waitFor(() =>
    expect(mutateAsync).toHaveBeenNthCalledWith(2, {
      ref: { backend: 'registry', registry_key: 'run_beat' },
      kwargs: { beat_id: 12 },
    })
  );
});

test('Condition tab Remove mode lists active instances then dispatches gm_remove_condition (#3431)', async () => {
  mutateAsync.mockResolvedValueOnce({
    backend: 'registry',
    deferred: false,
    success: true,
    message: 'listed',
    data: {
      conditions: [{ id: 8, name: 'Winded', severity: 1, rounds_remaining: 3, expires_at: null }],
    },
  });

  const user = userEvent.setup();
  render(<GMAdjudicationPanel scene={makeScene()} />);

  await user.selectOptions(screen.getByTestId('gm-adjudication-target-select'), '55');
  await user.click(screen.getByTestId('gm-tab-condition'));
  await user.selectOptions(screen.getByTestId('gm-condition-mode-select'), 'remove');

  await waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'gm_list_conditions' },
      kwargs: { target: 55 },
    })
  );
  await waitFor(() => expect(screen.getByText('Winded (severity 1)')).toBeInTheDocument());

  await user.selectOptions(screen.getByTestId('gm-condition-remove-select'), 'Winded');
  await user.type(screen.getByTestId('gm-condition-remove-reason'), 'served its purpose');
  await user.click(screen.getByTestId('gm-condition-remove-submit'));

  await waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'gm_remove_condition' },
      kwargs: { target: 55, condition: 'Winded', reason: 'served its purpose' },
    })
  );
});
