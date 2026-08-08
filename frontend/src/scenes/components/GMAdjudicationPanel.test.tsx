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

const mutateAsync = vi.fn((_body: DispatchBody) =>
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
