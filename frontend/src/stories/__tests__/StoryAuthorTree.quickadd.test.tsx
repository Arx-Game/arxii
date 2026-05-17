/**
 * StoryAuthorTree nimble quick-add wiring tests — Task F3
 *
 * F3 realises the design's "nimble in-session" requirement: a GM mid-session,
 * players go sideways → one click to graft a new beat or a new branch onto the
 * current episode, valid immediately (backbone no-reachability rule), no
 * backend. This is PURE FRONTEND WIRING of the EXISTING create dialogs:
 *
 *   - a "+ Beat" button on an episode row opens the existing BeatFormDialog
 *     in CREATE mode (no `beat` prop) with this episode preset
 *     (episodeId = episode.id). BeatFormDialog has its own suite — we assert
 *     only that the dialog opens in create mode here, NOT its internals.
 *   - a "+ Branch" button opens the existing TransitionFormDialog with
 *     source_episode preset to this episode (sourceEpisodeId = episode.id) and
 *     the target left to the author (nullable target = authoring frontier,
 *     which the backbone explicitly supports). TransitionFormDialog has its
 *     own suite — we assert only that the dialog opens with the correct source
 *     and that the target selector is empty/selectable, NOT its internals.
 *   - both reuse the EXISTING dialogs and their EXISTING props/open contracts
 *     (mirrors the DAG drag-connect / F2 mounting pattern). No new form
 *     components, no new endpoints, no dialog-internal changes.
 *
 * Mirrors the F2 (StoryAuthorTree.runcontrol) harness: mock `../api`'s
 * getGMQueue (the Resolve run-control local query) and `../queries` so every
 * hook the tree + the mounted CRUD dialogs touch is controllable, and
 * renderWithProviders for store/router/query context.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StoryAuthorTree } from '../components/StoryAuthorTree';
import type {
  Beat,
  ChapterList,
  EpisodeList,
  GMQueueEpisodeEntry,
  GMQueueResponse,
  Story,
} from '../types';

// ---------------------------------------------------------------------------
// Mocks — the tree renders the CRUD form dialogs too, which touch many
// `../queries` hooks. Spread the real module and override only the hooks
// we need to control (mirrors the F2 importOriginal pattern). The Resolve
// run-control uses a LOCAL useQuery against api.getGMQueue, so we mock
// `../api`'s getGMQueue directly — exactly as F2 / GMQueuePage.test does.
// ---------------------------------------------------------------------------

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getGMQueue: vi.fn(),
  };
});

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
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as api from '../api';
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
  scenes_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as EpisodeList;

// ---------------------------------------------------------------------------
// Mock harness
// ---------------------------------------------------------------------------

const noopMutation = {
  mutate: vi.fn(),
  isPending: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

function paginated<T>(results: T[]) {
  return { count: results.length, results, next: null, previous: null };
}

function setup({ beats = [] as Beat[] } = {}) {
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

  // No episodes ready to resolve — keeps the Resolve trigger out of the way
  // so the quick-add buttons are the only action-group affordances asserted.
  const gmQueueResponse: GMQueueResponse = {
    episodes_ready_to_run: [] as GMQueueEpisodeEntry[],
    pending_agm_claims: [],
    assigned_session_requests: [],
  };
  vi.mocked(api.getGMQueue).mockResolvedValue(gmQueueResponse);

  vi.mocked(queries.useDeleteChapter).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteEpisode).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteBeat).mockReturnValue(noopMutation);
  vi.mocked(queries.useDeleteTransition).mockReturnValue(noopMutation);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryAuthorTree nimble quick-add wiring — Task F3', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a "+ Beat" and a "+ Branch" quick-add button on the episode row', async () => {
    setup();

    renderWithProviders(<StoryAuthorTree story={story} />);

    const episodeRow = await screen.findByTestId('episode-row-author');
    // The Plus icon is aria-hidden, so the accessible name is the label text
    // alone ("Beat" / "Branch"). Anchored regexes avoid colliding with the
    // bare-icon "Add Beat" / "Edit episode" / "Delete Episode" buttons.
    expect(within(episodeRow).getByRole('button', { name: /^beat$/i })).toBeInTheDocument();
    expect(within(episodeRow).getByRole('button', { name: /^branch$/i })).toBeInTheDocument();
  });

  it('"+ Beat" opens BeatFormDialog in CREATE mode preset to this episode', async () => {
    const user = userEvent.setup();
    setup();

    renderWithProviders(<StoryAuthorTree story={story} />);

    const episodeRow = await screen.findByTestId('episode-row-author');
    await user.click(within(episodeRow).getByRole('button', { name: /^beat$/i }));

    // The EXISTING BeatFormDialog opens. CREATE mode (no `beat` prop): the
    // heading reads "Create Beat" (BeatFormDialog renders "Edit Beat" when a
    // beat is passed). We assert the wiring — open + create mode — not the
    // dialog's internal fields (covered by BeatFormDialog's own suite).
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: /create beat/i })).toBeInTheDocument();
  });

  it('"+ Branch" opens TransitionFormDialog with this episode as the source, target unset', async () => {
    const user = userEvent.setup();
    setup();

    renderWithProviders(<StoryAuthorTree story={story} />);

    const episodeRow = await screen.findByTestId('episode-row-author');
    await user.click(within(episodeRow).getByRole('button', { name: /^branch$/i }));

    // The EXISTING TransitionFormDialog opens. CREATE mode (no `transition`
    // prop): the heading reads "Create Transition". The source episode is
    // preset — TransitionFormDialog renders the read-only source id (100).
    // The target is left to the author (frontier placeholder visible). We
    // assert the wiring — open + correct source + selectable/empty target —
    // not the dialog's internals (covered by its own suite).
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: /create transition/i })).toBeInTheDocument();
    expect(within(dialog).getByText(/source episode id:/i)).toHaveTextContent(String(episode.id));
    expect(within(dialog).getByText(/advance to the authoring frontier/i)).toBeInTheDocument();
  });
});
