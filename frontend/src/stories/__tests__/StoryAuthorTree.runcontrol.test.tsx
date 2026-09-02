/**
 * StoryAuthorTree run-control wiring tests — Task F2
 *
 * F2 makes the author page an author-AND-run cockpit: the GM marks beats
 * from the same page they author it on. The MarkBeatDialog component +
 * its endpoint already exist and are tested in their own suite — this
 * task is PURE WIRING:
 *
 *   - a GM_MARKED beat row exposes the existing MarkBeatDialog "Mark"
 *     trigger, gated EXACTLY as BeatRow already self-gates it
 *     (`isGmMarked && !isResolved && beat.can_mark`). A beat without
 *     can_mark shows no Mark trigger.
 *   - Contribute is intentionally NOT mounted here: ContributeBeatDialog
 *     needs a characterSheetId + current contribution total, neither of
 *     which the author tree context has, and fabricating a sheet id is
 *     forbidden by the task.
 *
 * #3565 retired the "Resolve" run-control trigger (and ResolveEpisodeDialog
 * entirely): every transition now fires automatically off its routing
 * predicate, so there is no GM-choice set left to resolve from the author
 * tree. Authoring the next node (beat/transition) in the tree is the only
 * remaining GM action at the frontier.
 *
 * These tests assert the WIRING (trigger presence/gating + the dialog
 * opening with the correct beat identity), NOT the dialog's internal
 * submit behaviour (covered by MarkBeatDialog's own suite). Mirrors the
 * ProgressStateBanner (F1) harness: mock `../queries` so every hook the
 * tree + mounted dialogs touch is controllable, and renderWithProviders
 * for store/router/query context.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StoryAuthorTree } from '../components/StoryAuthorTree';
import type { Beat, ChapterList, EpisodeList, Story } from '../types';

// ---------------------------------------------------------------------------
// Mocks — the tree renders the CRUD form dialogs too, which touch many
// `../queries` hooks. Spread the real module and override only the hooks
// we need to control (mirrors the importOriginal pattern vitest recommends).
// ---------------------------------------------------------------------------

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useChapterList: vi.fn(),
    useEpisodeList: vi.fn(),
    useBeatList: vi.fn(),
    useTransitionList: vi.fn(),
    useDeleteChapter: vi.fn(),
    useDeleteEpisode: vi.fn(),
    useDeleteBeat: vi.fn(),
    useDeleteTransition: vi.fn(),
    // Run-control wiring (F2):
    useMarkBeat: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const story: Story = {
  id: 1,
  title: 'Who Am I?',
  description: 'A personal identity story.',
  scope: 'character',
  status: 'active',
  privacy: 'public',
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 1,
  tenure_id: null,
  chapters_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  completed_at: null,
  primary_table: null,
};

const chapter: ChapterList = {
  id: 10,
  story: '1',
  title: 'Act I',
  order: 1,
  is_active: true,
  episodes_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as ChapterList;

const episode: EpisodeList = {
  id: 100,
  chapter: '10',
  title: 'The Reckoning',
  order: 1,
  scenes_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as EpisodeList;

function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return {
    id: 200,
    episode: 100,
    episode_title: 'The Reckoning',
    chapter_title: 'Act I',
    story_id: 1,
    story_title: 'Who Am I?',
    predicate_type: 'gm_marked',
    outcome: 'unsatisfied',
    visibility: 'hinted',
    internal_description: 'The villain escapes or is captured',
    player_hint: 'Confront the villain',
    player_resolution_text: undefined,
    order: 1,
    required_level: undefined,
    required_achievement: undefined,
    required_condition_template: undefined,
    required_codex_entry: undefined,
    referenced_story: undefined,
    referenced_milestone_type: undefined,
    referenced_chapter: undefined,
    referenced_episode: undefined,
    required_points: undefined,
    agm_eligible: false,
    deadline: undefined,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    can_mark: true,
    ...overrides,
  } as Beat;
}

// ---------------------------------------------------------------------------
// Mock harness
// ---------------------------------------------------------------------------

interface SetupOptions {
  beats?: Beat[];
}

const noopMutation = {
  mutate: vi.fn(),
  isPending: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

function paginated<T>(results: T[]) {
  return { count: results.length, results, next: null, previous: null };
}

function setup({ beats = [makeBeat()] }: SetupOptions = {}) {
  vi.mocked(queries.useChapterList).mockReturnValue({
    data: paginated([chapter]),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: paginated([episode]),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useBeatList).mockReturnValue({
    data: paginated(beats),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useTransitionList).mockReturnValue({
    data: paginated([]),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);

  vi.mocked(queries.useDeleteChapter).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteEpisode).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteBeat).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteTransition).mockReturnValue(noopMutation);
  vi.mocked(queries.useMarkBeat).mockReturnValue(noopMutation);
}

async function expandEpisode(user: ReturnType<typeof userEvent.setup>) {
  // Chapter row starts expanded; expand the episode row to reveal beats.
  const episodeRow = await screen.findByTestId('episode-row-author');
  const toggle = within(episodeRow).getByRole('button', { name: /the reckoning/i });
  await user.click(toggle);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryAuthorTree run-control wiring — Task F2', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the Mark trigger on a GM_MARKED beat row when can_mark is true', async () => {
    const user = userEvent.setup();
    setup({ beats: [makeBeat({ can_mark: true })] });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    expect(within(beatRow).getByRole('button', { name: /^mark$/i })).toBeInTheDocument();
  });

  it('does NOT show the Mark trigger when can_mark is false', async () => {
    const user = userEvent.setup();
    setup({ beats: [makeBeat({ can_mark: false })] });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    expect(within(beatRow).queryByRole('button', { name: /^mark$/i })).not.toBeInTheDocument();
  });

  it('does NOT show the Mark trigger for a non-GM_MARKED beat', async () => {
    const user = userEvent.setup();
    setup({
      beats: [makeBeat({ predicate_type: 'aggregate_threshold', can_mark: true })],
    });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    expect(within(beatRow).queryByRole('button', { name: /^mark$/i })).not.toBeInTheDocument();
  });

  it('does NOT show the Mark trigger when the beat is already resolved', async () => {
    const user = userEvent.setup();
    setup({ beats: [makeBeat({ can_mark: true, outcome: 'success' })] });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    expect(within(beatRow).queryByRole('button', { name: /^mark$/i })).not.toBeInTheDocument();
  });

  it('opens MarkBeatDialog for THAT beat when the Mark trigger is clicked', async () => {
    const user = userEvent.setup();
    setup({ beats: [makeBeat({ can_mark: true })] });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    await user.click(within(beatRow).getByRole('button', { name: /^mark$/i }));

    // MarkBeatDialog opens with the beat's identity in its title.
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: /mark beat/i })).toBeInTheDocument();
    expect(within(dialog).getByText(/confront the villain/i)).toBeInTheDocument();
  });

  it('does NOT show a Resolve trigger on an episode row (retired by #3565)', async () => {
    setup();

    renderWithProviders(<StoryAuthorTree story={story} />);

    const episodeRow = await screen.findByTestId('episode-row-author');
    expect(
      within(episodeRow).queryByRole('button', { name: /^resolve$/i })
    ).not.toBeInTheDocument();
  });
});
