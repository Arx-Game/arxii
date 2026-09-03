/**
 * BeatFormDialog Tests — Task 9.2
 *
 * Covers:
 *  - gm_marked predicate type: no config fields
 *  - character_level_at_least: required_level field appears
 *  - aggregate_threshold: required_points field appears
 *  - story_at_milestone: milestone-type-conditional fields
 *  - Switching predicate type clears config values
 *  - Submit happy path for gm_marked
 *  - Submit happy path for aggregate_threshold
 *  - DRF validation errors surface inline
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { BeatFormDialog } from '../components/BeatFormDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateBeat: vi.fn(),
  useUpdateBeat: vi.fn(),
  useCreateBeatScenario: vi.fn(),
  useStoryList: vi.fn(),
  useChapterList: vi.fn(),
  useEpisodeList: vi.fn(),
  useBeatReadiness: vi.fn(),
  useOpenBeatActivation: vi.fn(),
  useBeatConsequencePools: vi.fn(),
  useConsequencePoolDetail: vi.fn(),
}));

// StakesPanel (#3561) mounts after the Scenario section in edit mode; its
// own suite (`__tests__/stakes/StakesPanel.test.tsx`) covers its behavior,
// so this file stubs it out rather than adding its whole query surface
// (useStakes/useStakeTemplates/useCreateStake/useGMProfileMine/...) to this
// file's mock.
vi.mock('../components/stakes/StakesPanel', () => ({
  StakesPanel: () => <div data-testid="stub-stakes-panel" />,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// #3425 session prep — creature/situation/challenge catalog pickers.
vi.mock('@/combat/queries', () => ({
  useCreatureTemplates: vi.fn(() => ({
    data: [{ id: 1, name: 'Gorehorn', tier: 'boss', description: '', has_phases: true }],
  })),
}));

vi.mock('@/gm-adjudication/queries', () => ({
  useSituationTemplateCatalog: vi.fn(() => ({
    data: [{ id: 5, name: 'Ambush', category: 1, category_name: 'Combat' }],
  })),
  useChallengeTemplateCatalog: vi.fn(() => ({
    data: [{ id: 9, name: 'Locked Gate', category: 1, category_name: 'Exploration' }],
  })),
}));

// #3562 - the requesting account's own GM profile (risk cap).
vi.mock('@/gm/queries', () => ({
  useGMProfileMine: vi.fn(),
}));

// #3562 - required_mission's EntitySearchField search/resolve wrappers.
vi.mock('@/missions/api', () => ({
  listMissionTemplates: vi.fn(),
  getMissionTemplate: vi.fn(),
}));

// Mock the auth/account selector hook the component uses to determine
// whether the current user is staff (controls the risk control's disabled
// state). Mirrors the @/store/hooks mocking pattern used elsewhere
// (e.g. SceneDetailPage.test.tsx).
const accountState: { is_staff: boolean } = { is_staff: false };

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({
      game: { active: null },
      auth: {
        account: {
          id: 1,
          username: 'testuser',
          is_staff: accountState.is_staff,
          available_characters: [],
        },
      },
    })
  ),
  useAccount: vi.fn(() => ({
    id: 1,
    username: 'testuser',
    is_staff: accountState.is_staff,
    available_characters: [],
  })),
}));

import * as queries from '../queries';
import * as gmQueries from '@/gm/queries';
import * as missionsApi from '@/missions/api';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationMock(hookName: 'useCreateBeat' | 'useUpdateBeat' | 'useCreateBeatScenario') {
  const mutateMock = vi.fn();
  vi.mocked(queries[hookName]).mockReturnValue({
    mutate: mutateMock,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutateMock;
}

function setupMocks() {
  const createMock = makeMutationMock('useCreateBeat');
  makeMutationMock('useUpdateBeat');
  makeMutationMock('useCreateBeatScenario');

  vi.mocked(queries.useStoryList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryList>);

  vi.mocked(queries.useChapterList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useChapterList>);

  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useEpisodeList>);

  // #3562 - readiness/lock (edit mode only; harmless defaults in create
  // mode since the component gates both queries on `isEdit`), the
  // beat-scoped consequence pool catalog/detail, and the GM profile risk
  // cap. Individual tests override any of these as needed.
  vi.mocked(queries.useBeatReadiness).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useBeatReadiness>);

  vi.mocked(queries.useOpenBeatActivation).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useOpenBeatActivation>);

  vi.mocked(queries.useBeatConsequencePools).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useBeatConsequencePools>);

  vi.mocked(queries.useConsequencePoolDetail).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useConsequencePoolDetail>);

  vi.mocked(gmQueries.useGMProfileMine).mockReturnValue({
    data: null,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof gmQueries.useGMProfileMine>);

  vi.mocked(missionsApi.listMissionTemplates).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });

  return createMock;
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  episodeId: 42,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BeatFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    accountState.is_staff = false;
  });

  it('renders Create Beat dialog', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Create Beat' })).toBeInTheDocument();
  });

  it('outcome_tier is selected by default and shows no extra config (#3565)', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // outcome_tier radio should be selected; GM-choice retired, most beats
    // now resolve off a scenario/fight/check outcome rather than a manual mark.
    const predicateGroup = screen.getByTestId('predicate-type-group');
    const outcomeTierRadio = within(predicateGroup).getByRole('radio', { name: /outcome tier/i });
    expect(outcomeTierRadio).toBeChecked();

    // No level/points fields visible
    expect(screen.queryByLabelText(/required level/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/required points/i)).not.toBeInTheDocument();
  });

  it('character_level_at_least predicate shows required_level field', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    const levelRadio = within(predicateGroup).getByRole('radio', {
      name: /character level at least/i,
    });
    await user.click(levelRadio);

    expect(screen.getByLabelText(/required level/i)).toBeInTheDocument();
  });

  it('aggregate_threshold predicate shows required_points field', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    const thresholdRadio = within(predicateGroup).getByRole('radio', {
      name: /aggregate threshold/i,
    });
    await user.click(thresholdRadio);

    expect(screen.getByLabelText(/required points/i)).toBeInTheDocument();
  });

  it('switching predicate type clears previous config value', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');

    // Select character_level_at_least and fill required_level
    await user.click(
      within(predicateGroup).getByRole('radio', { name: /character level at least/i })
    );
    const levelInput = screen.getByLabelText(/required level/i);
    await user.type(levelInput, '10');
    expect((levelInput as HTMLInputElement).value).toBe('10');

    // Switch to aggregate_threshold — required_level field gone, required_points appears blank
    await user.click(within(predicateGroup).getByRole('radio', { name: /aggregate threshold/i }));
    expect(screen.queryByLabelText(/required level/i)).not.toBeInTheDocument();
    const pointsInput = screen.getByLabelText(/required points/i);
    expect((pointsInput as HTMLInputElement).value).toBe('');
  });

  it('story_at_milestone shows milestone-type selector', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(within(predicateGroup).getByRole('radio', { name: /story at milestone/i }));

    // Referenced Story and Milestone Type comboboxes should appear
    expect(screen.getByText('Referenced Story')).toBeInTheDocument();
    expect(screen.getByText('Milestone Type')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // #3562 - ninth predicate: faction_standing_at_least (Society | Organization XOR)
  // -------------------------------------------------------------------------

  it('faction_standing_at_least shows the Society/Organization XOR picker and submits one id', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 200 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(
      within(predicateGroup).getByRole('radio', { name: /faction standing at least/i })
    );

    // Society is the default side of the XOR.
    expect(screen.getByLabelText(/required society id/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/required organization id/i)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/required society id/i), '12');
    await user.type(screen.getByLabelText(/required standing/i), '50');
    await user.type(screen.getByLabelText(/internal description/i), 'Standing beat');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          predicate_type: 'faction_standing_at_least',
          required_society: 12,
          required_organization: null,
          required_standing: 50,
        }),
        expect.any(Object)
      );
    });
  });

  it('faction_standing_at_least: switching to Organization submits required_organization instead', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 201 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(
      within(predicateGroup).getByRole('radio', { name: /faction standing at least/i })
    );

    const factionScopeGroup = screen.getByTestId('faction-scope-group');
    await user.click(within(factionScopeGroup).getByRole('radio', { name: /organization/i }));

    expect(screen.getByLabelText(/required organization id/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/required society id/i)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/required organization id/i), '7');
    await user.type(screen.getByLabelText(/required standing/i), '25');
    await user.type(screen.getByLabelText(/internal description/i), 'Org standing beat');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          predicate_type: 'faction_standing_at_least',
          required_society: null,
          required_organization: 7,
          required_standing: 25,
        }),
        expect.any(Object)
      );
    });
  });

  it('submits gm_marked beat with correct payload', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 99 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // Default predicate is outcome_tier (#3565); explicitly pick gm_marked
    // for this test.
    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(within(predicateGroup).getByRole('radio', { name: /gm marked/i }));

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'A GM-marked beat description');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          episode: 42,
          predicate_type: 'gm_marked',
          internal_description: 'A GM-marked beat description',
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Beat created');
    });
  });

  it('submits aggregate_threshold beat with required_points', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 100 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(within(predicateGroup).getByRole('radio', { name: /aggregate threshold/i }));

    const pointsInput = screen.getByLabelText(/required points/i);
    await user.type(pointsInput, '100');

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Threshold beat');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          predicate_type: 'aggregate_threshold',
          required_points: 100,
        }),
        expect.any(Object)
      );
    });
  });

  it('surfaces DRF validation error inline', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    const mockErrorResponse = {
      json: () => Promise.resolve({ player_hint: ['This field is too long.'] }),
    };

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // Fill in the required internal description to pass HTML5 validation
    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Some beat description');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(screen.getByText(/this field is too long/i)).toBeInTheDocument();
    });

    // Dialog stays open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('converts deadline to UTC ISO string before submission', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 101 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Beat with deadline');

    // Fill in the deadline datetime-local input
    const deadlineInput = screen.getByLabelText(/deadline/i);
    await user.type(deadlineInput, '2026-05-01T14:00');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          // Must be a full ISO 8601 string with timezone offset, not a bare local string.
          deadline: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/),
        }),
        expect.any(Object)
      );
    });
  });

  it('renders in edit mode pre-populated', () => {
    setupMocks();
    const existingBeat = {
      id: 5,
      episode: 42,
      predicate_type: 'character_level_at_least' as const,
      required_level: 7,
      outcome: 'unsatisfied' as const,
      visibility: 'hinted' as const,
      internal_description: 'Must be at least level 7',
      player_hint: 'A level threshold',
      player_resolution_text: undefined,
      order: 1,
      agm_eligible: false,
      deadline: null,
      required_achievement: null,
      required_condition_template: null,
      required_codex_entry: null,
      referenced_story: null,
      referenced_milestone_type: undefined,
      referenced_chapter: null,
      referenced_episode: null,
      required_points: null,
      episode_title: 'Test Episode',
      chapter_title: 'Chapter 1',
      story_id: 1,
      story_title: 'Test Story',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      can_mark: false,
      scenario: null,
      opponent_lines: [],
      staged_templates: [],
    };

    renderWithProviders(<BeatFormDialog {...defaultProps} beat={existingBeat} />);

    expect(screen.getByText('Edit Beat')).toBeInTheDocument();
    const descInput = screen.getByLabelText(/internal description/i);
    expect((descInput as HTMLInputElement).value).toBe('Must be at least level 7');
    expect(screen.getByLabelText(/required level/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Task E1 — kind / advances / risk controls
  // -------------------------------------------------------------------------

  it('renders kind / advances / risk controls with correct defaults', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // Kind select — defaults to "task" per backbone model default
    const kindSelect = screen.getByLabelText(/^kind$/i) as HTMLSelectElement;
    expect(kindSelect).toBeInTheDocument();
    expect(kindSelect.value).toBe('task');
    expect(within(kindSelect).getByRole('option', { name: /situation/i })).toBeInTheDocument();
    expect(within(kindSelect).getByRole('option', { name: /encounter/i })).toBeInTheDocument();
    expect(within(kindSelect).getByRole('option', { name: /task/i })).toBeInTheDocument();
    expect(within(kindSelect).getByRole('option', { name: /requirement/i })).toBeInTheDocument();

    // Advances toggle — default checked (true)
    const advancesInput = screen.getByLabelText(/advances the plot/i) as HTMLInputElement;
    expect(advancesInput).toBeInTheDocument();
    expect(advancesInput).toBeChecked();
    expect(
      screen.getByText(/off = tangent: recorded for history, never gates a transition/i)
    ).toBeInTheDocument();

    // Risk select — defaults to "none" per backbone model default
    const riskSelect = screen.getByLabelText(/^risk$/i) as HTMLSelectElement;
    expect(riskSelect).toBeInTheDocument();
    expect(riskSelect.value).toBe('none');
    expect(within(riskSelect).getByRole('option', { name: /^none$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^low$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^moderate$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^high$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^extreme$/i })).toBeInTheDocument();
    expect(screen.getByText(/only gms may set risk/i)).toBeInTheDocument();
  });

  it('disables the risk select for non-staff users with no GM profile', () => {
    accountState.is_staff = false;
    setupMocks();
    vi.mocked(gmQueries.useGMProfileMine).mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gmQueries.useGMProfileMine>);
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const riskSelect = screen.getByLabelText(/^risk$/i) as HTMLSelectElement;
    expect(riskSelect).toBeDisabled();
    expect(screen.getByText(/only gms may set risk/i)).toBeInTheDocument();
  });

  it('enables the risk select for staff users', () => {
    accountState.is_staff = true;
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const riskSelect = screen.getByLabelText(/^risk$/i) as HTMLSelectElement;
    expect(riskSelect).toBeEnabled();
  });

  it('shows the full risk ladder and "Staff may set any risk" for staff (#3562)', () => {
    accountState.is_staff = true;
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const riskSelect = screen.getByLabelText(/^risk$/i) as HTMLSelectElement;
    expect(within(riskSelect).getByRole('option', { name: /^none$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^low$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^moderate$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^high$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^extreme$/i })).toBeInTheDocument();
    expect(screen.getByText(/staff may set any risk/i)).toBeInTheDocument();
  });

  it("caps the risk options to a GM profile's max_beat_risk (#3562)", () => {
    accountState.is_staff = false;
    setupMocks();
    vi.mocked(gmQueries.useGMProfileMine).mockReturnValue({
      data: {
        id: 1,
        level: 'junior',
        level_display: 'Junior',
        max_beat_risk: 'low',
        allow_custom_stakes: false,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gmQueries.useGMProfileMine>);
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const riskSelect = screen.getByLabelText(/^risk$/i) as HTMLSelectElement;
    expect(riskSelect).toBeEnabled();
    expect(within(riskSelect).getByRole('option', { name: /^none$/i })).toBeInTheDocument();
    expect(within(riskSelect).getByRole('option', { name: /^low$/i })).toBeInTheDocument();
    expect(
      within(riskSelect).queryByRole('option', { name: /^moderate$/i })
    ).not.toBeInTheDocument();
    expect(within(riskSelect).queryByRole('option', { name: /^high$/i })).not.toBeInTheDocument();
    expect(
      within(riskSelect).queryByRole('option', { name: /^extreme$/i })
    ).not.toBeInTheDocument();
    expect(screen.getByText(/your gm level allows up to low/i)).toBeInTheDocument();
  });

  it('includes kind / advances / risk in the create submit body', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 102 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Beat with metadata');

    // Change kind to encounter
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'encounter');

    // Toggle advances off (default true → false)
    await user.click(screen.getByLabelText(/advances the plot/i));

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'encounter',
          advances: false,
          risk: 'none',
        }),
        expect.any(Object)
      );
    });
  });

  it('lets staff set risk and submits the value', async () => {
    accountState.is_staff = true;
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 103 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Risky beat');

    await user.selectOptions(screen.getByLabelText(/^risk$/i), 'high');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          risk: 'high',
        }),
        expect.any(Object)
      );
    });
  });

  it('prefills kind / advances / risk from an existing beat on edit', () => {
    setupMocks();
    const existingBeat = {
      id: 6,
      episode: 42,
      predicate_type: 'gm_marked' as const,
      kind: 'requirement' as const,
      advances: false,
      risk: 'high' as const,
      outcome: 'unsatisfied' as const,
      visibility: 'hinted' as const,
      internal_description: 'A requirement beat',
      player_hint: '',
      player_resolution_text: undefined,
      order: 2,
      agm_eligible: false,
      deadline: null,
      required_level: null,
      required_achievement: null,
      required_condition_template: null,
      required_codex_entry: null,
      referenced_story: null,
      referenced_milestone_type: undefined,
      referenced_chapter: null,
      referenced_episode: null,
      required_points: null,
      episode_title: 'Test Episode',
      chapter_title: 'Chapter 1',
      story_id: 1,
      story_title: 'Test Story',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      can_mark: false,
      scenario: null,
      opponent_lines: [],
      staged_templates: [],
    };

    renderWithProviders(<BeatFormDialog {...defaultProps} beat={existingBeat} />);

    expect((screen.getByLabelText(/^kind$/i) as HTMLSelectElement).value).toBe('requirement');
    expect(screen.getByLabelText(/advances the plot/i)).not.toBeChecked();
    expect((screen.getByLabelText(/^risk$/i) as HTMLSelectElement).value).toBe('high');
  });

  // -------------------------------------------------------------------------
  // #3425 — session prep: opponent lines (kind=encounter) / staged templates
  // (kind=situation) repeatable rows.
  // -------------------------------------------------------------------------

  it('kind=encounter shows the opponent lines editor, hidden by default', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    expect(screen.queryByTestId('beat-opponent-lines')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'encounter');
    expect(screen.getByTestId('beat-opponent-lines')).toBeInTheDocument();
    expect(screen.queryByTestId('beat-staged-templates')).not.toBeInTheDocument();
  });

  it('kind=situation shows the staged templates editor, hidden by default', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'situation');
    expect(screen.getByTestId('beat-staged-templates')).toBeInTheDocument();
    expect(screen.queryByTestId('beat-opponent-lines')).not.toBeInTheDocument();
  });

  it('submits an encounter beat with an authored opponent line', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 101 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/internal description/i), 'A fight beat');
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'encounter');
    await user.click(screen.getByRole('button', { name: /add opponent/i }));
    await user.selectOptions(screen.getByTestId('beat-opponent-line-creature-0'), '1');
    await user.clear(screen.getByTestId('beat-opponent-line-count-0'));
    await user.type(screen.getByTestId('beat-opponent-line-count-0'), '2');
    await user.type(screen.getByTestId('beat-opponent-line-position-0'), 'front');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'encounter',
          opponent_lines: [{ creature_template: 1, count: 2, position_name: 'front', order: 0 }],
        }),
        expect.any(Object)
      );
    });
  });

  it('submits a situation beat with an authored staged situation template', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 102 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/internal description/i), 'A staged beat');
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'situation');
    await user.click(screen.getByRole('button', { name: /add staged template/i }));
    await user.selectOptions(screen.getByTestId('beat-staged-template-situation-0'), '5');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'situation',
          staged_templates: [{ situation_template: 5, challenge_template: null, order: 0 }],
        }),
        expect.any(Object)
      );
    });
  });

  it('removing an opponent line row drops it from the payload', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 103 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/internal description/i), 'A fight beat');
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'encounter');
    await user.click(screen.getByRole('button', { name: /add opponent/i }));
    await user.click(screen.getByTestId('beat-opponent-line-remove-0'));
    expect(screen.queryByTestId('beat-opponent-line-row-0')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'encounter', opponent_lines: [] }),
        expect.any(Object)
      );
    });
  });

  // -------------------------------------------------------------------------
  // #3565 - Scenario section (SITUATION/TASK beats, edit mode only)
  // -------------------------------------------------------------------------

  function makeSituationBeat(
    overrides: Partial<{
      scenario: { template_id: number; name: string; option_keys: string[] } | null;
    }> = {}
  ) {
    return {
      id: 7,
      episode: 42,
      predicate_type: 'outcome_tier' as const,
      kind: 'situation' as const,
      advances: true,
      risk: 'none' as const,
      outcome: 'unsatisfied' as const,
      visibility: 'hinted' as const,
      internal_description: 'The ambush at the crossroads',
      player_hint: '',
      player_resolution_text: undefined,
      order: 1,
      agm_eligible: false,
      deadline: null,
      required_level: null,
      required_achievement: null,
      required_condition_template: null,
      required_codex_entry: null,
      referenced_story: null,
      referenced_milestone_type: undefined,
      referenced_chapter: null,
      referenced_episode: null,
      required_points: null,
      episode_title: 'Test Episode',
      chapter_title: 'Chapter 1',
      story_id: 1,
      story_title: 'Test Story',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      can_mark: false,
      scenario: null,
      opponent_lines: [],
      staged_templates: [],
      ...overrides,
    };
  }

  it('create mode tells the author to save first (no Design scenario button)', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);
    expect(screen.getByText(/save the beat, then design its scenario/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /design scenario/i })).not.toBeInTheDocument();
  });

  it('edit mode with scenario: null renders Design scenario and calls the mutation on submit', async () => {
    const user = userEvent.setup();
    setupMocks();
    const scenarioMutate = makeMutationMock('useCreateBeatScenario');
    scenarioMutate.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 55, name: 'The Ambush' });
    });

    const beat = makeSituationBeat();
    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    const designBtn = screen.getByTestId('design-scenario-btn');
    expect(designBtn).toBeInTheDocument();
    await user.click(designBtn);

    await user.type(screen.getByLabelText(/^name$/i), 'The Ambush');
    await user.type(screen.getByLabelText(/^summary$/i), 'Bandits strike at dusk.');

    await user.click(screen.getByTestId('confirm-design-scenario'));

    await waitFor(() => {
      expect(scenarioMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          beatId: 7,
          name: 'The Ambush',
          summary: 'Bandits strike at dusk.',
          risk_tier: 1,
        }),
        expect.any(Object)
      );
    });

    // On success, the section shows the new scenario's name + Open canvas link.
    await waitFor(() => {
      expect(screen.getByText('The Ambush')).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /open canvas/i })).toHaveAttribute(
      'href',
      '/stories/scenarios/55/canvas'
    );
  });

  it('edit mode with a scenario already set renders Open canvas with the right href', () => {
    setupMocks();
    const beat = makeSituationBeat({
      scenario: { template_id: 88, name: 'The Boss Fight', option_keys: ['negotiate', 'fight'] },
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    expect(screen.getByText('The Boss Fight')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open canvas/i })).toHaveAttribute(
      'href',
      '/stories/scenarios/88/canvas'
    );
    expect(screen.queryByTestId('design-scenario-btn')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // #3562 - consequence pools, readiness, the stakes-contract lock, and the
  // required_mission picker.
  // -------------------------------------------------------------------------

  it('the consequence pool picker submits success_consequences and renders entries from a mocked detail', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 300 });
    });

    vi.mocked(queries.useBeatConsequencePools).mockReturnValue({
      data: [{ id: 7, name: 'Wild Magic Surge', description: '' }],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useBeatConsequencePools>);

    vi.mocked(queries.useConsequencePoolDetail).mockReturnValue({
      data: {
        id: 7,
        name: 'Wild Magic Surge',
        description: '',
        entries: [
          {
            consequence_id: 1,
            name: 'Arcane Backlash',
            outcome_tier: { id: 1, name: 'Severe', success_level: -2 },
            effect_types: ['condition'],
            character_loss: false,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useConsequencePoolDetail>);

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/internal description/i), 'Consequence beat');
    await user.selectOptions(screen.getByLabelText('Success'), '7');

    expect(screen.getByTestId('consequence-pool-entries-7')).toHaveTextContent('Arcane Backlash');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({ success_consequences: 7 }),
        expect.any(Object)
      );
    });
  });

  it('shows the readiness strip with problems, advisories, and effective risk in edit mode', () => {
    setupMocks();
    vi.mocked(queries.useBeatReadiness).mockReturnValue({
      data: {
        is_staked: true,
        is_ready: false,
        problems: ['Missing target_level.'],
        advisories: ['Consider raising the target level.'],
        declared_risk: 'moderate',
        effective_risk: 'low',
        locked: false,
        locked_at: null,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useBeatReadiness>);

    const beat = makeSituationBeat();
    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    const strip = screen.getByTestId('beat-readiness-strip');
    expect(strip).toHaveTextContent('Not ready');
    expect(strip).toHaveTextContent('Missing target_level.');
    expect(strip).toHaveTextContent('Consider raising the target level.');
    expect(strip).toHaveTextContent('Effective risk for the table: Low');
  });

  it('the lock banner disables risk, target level, and the three pool controls while an activation is open', () => {
    accountState.is_staff = true;
    setupMocks();
    vi.mocked(queries.useOpenBeatActivation).mockReturnValue({
      data: [
        {
          id: 1,
          beat: 7,
          locked_at: '2026-09-01T12:00:00Z',
          resolved_at: null,
          party_average_level: 5,
          declared_target_level: 5,
          declared_risk: 'moderate',
          effective_risk: 'moderate',
          is_ready: true,
          readiness_notes: '',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useOpenBeatActivation>);

    const beat = makeSituationBeat();
    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    expect(screen.getByTestId('beat-lock-banner')).toHaveTextContent(
      'Locked while the scene runs (since 2026-09-01T12:00:00Z)'
    );
    expect(screen.getByLabelText(/^risk$/i)).toBeDisabled();
    expect(screen.getByLabelText(/target level/i)).toBeDisabled();
    expect(screen.getByLabelText('Success')).toBeDisabled();
    expect(screen.getByLabelText('Failure')).toBeDisabled();
    expect(screen.getByLabelText('Expired')).toBeDisabled();
  });

  it('required_mission search calls listMissionTemplates with the typed name', async () => {
    const user = userEvent.setup();
    setupMocks();
    vi.mocked(missionsApi.listMissionTemplates).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 9, name: 'The Long Watch', story_id: null, risk_tier: 2 }],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const beat = makeSituationBeat();
    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    const missionInput = screen.getByLabelText(/required mission/i);
    await user.type(missionInput, 'Watch');

    await waitFor(() => {
      expect(missionsApi.listMissionTemplates).toHaveBeenCalledWith({
        name: 'Watch',
        page_size: 20,
      });
    });

    expect(await screen.findByText('The Long Watch')).toBeInTheDocument();
  });

  it('clears required_mission from the payload and the picker when kind switches away from situation/task (fix round 1)', async () => {
    const user = userEvent.setup();
    setupMocks();
    const updateMock = makeMutationMock('useUpdateBeat');
    updateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 7 });
    });

    vi.mocked(missionsApi.listMissionTemplates).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 9, name: 'The Long Watch', story_id: null, risk_tier: 2 }],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const beat = makeSituationBeat();
    renderWithProviders(<BeatFormDialog {...defaultProps} beat={beat} />);

    // Pick a required mission while the beat is still SITUATION.
    const missionInput = screen.getByLabelText(/required mission/i);
    await user.type(missionInput, 'Watch');
    await user.click(await screen.findByText('The Long Watch'));
    expect((missionInput as HTMLInputElement).value).toBe('The Long Watch');

    // Switch kind away from situation/task - the picker disappears (state cleared)
    // - then submit: the payload must not silently carry the stale FK.
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'encounter');
    expect(screen.queryByLabelText(/required mission/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /save beat/i }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 7,
          data: expect.objectContaining({ required_mission: null }),
        }),
        expect.any(Object)
      );
    });

    // Switching back to a kind that shows the picker again must not resurrect
    // the cleared pick - the picker reflects the (now null) state, not a stale echo.
    await user.selectOptions(screen.getByLabelText(/^kind$/i), 'task');
    const missionInputAgain = screen.getByLabelText(/required mission/i) as HTMLInputElement;
    expect(missionInputAgain.value).toBe('');
  });
});
