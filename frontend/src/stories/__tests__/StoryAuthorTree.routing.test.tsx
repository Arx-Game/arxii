/**
 * StoryAuthorTree routing rule / routing problem tests - #3563 Task 6.
 *
 * The author tree is where a GM designs routing, so each transition row
 * shows its own routing rule text (or "Always eligible" when it has none)
 * and each episode row surfaces a badge when the backend reports routing
 * problems for it. Both read fields that #3563's earlier tasks already put
 * on the wire: `Transition.required_outcomes` and
 * `EpisodeList.routing_problems`.
 *
 * Mirrors the F2/F3 harness (StoryAuthorTree.runcontrol.test.tsx /
 * StoryAuthorTree.quickadd.test.tsx): mock `../api` and `../queries` so
 * every hook the tree + mounted CRUD dialogs touch is controllable, and
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
  Transition,
} from '../types';

// ---------------------------------------------------------------------------
// Mocks - the tree renders the CRUD form dialogs too, which touch many
// `../queries` hooks. Spread the real module and override only the hooks
// we need to control (mirrors the F2/F3 importOriginal pattern).
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
  scenes_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as EpisodeList;

const transition: Transition = {
  id: 500,
  source_episode: episode.id,
  source_episode_title: episode.title,
  target_episode: 101,
  target_episode_title: 'The Aftermath',
  connection_type: 'therefore',
  connection_summary: 'They advance',
  order: 1,
  created_at: '2026-01-01T00:00:00Z',
} as Transition;

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

// mockEpisodesFor / mockTransitionsFor: neither StoryAuthorTree.quickadd.test.tsx
// nor .runcontrol.test.tsx factors these into named helpers - both set
// `vi.mocked(queries.useEpisodeList/useTransitionList).mockReturnValue(...)`
// inline inside a combined `setup()`. Routing needs per-test overrides for
// just these two hooks (episodes with routing_problems, transitions with
// required_outcomes), so they're pulled out here under the brief's
// placeholder names; `setup()` below still sets every other hook exactly as
// the sibling files do.
function mockEpisodesFor(_chapterId: number, episodes: EpisodeList[]) {
  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: paginated(episodes),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockTransitionsFor(_sourceEpisodeId: number, transitions: Transition[]) {
  vi.mocked(queries.useTransitionList).mockReturnValue({
    data: paginated(transitions),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function setup({ beats = [] as Beat[] } = {}) {
  vi.mocked(queries.useChapterList).mockReturnValue({
    data: paginated([chapter]),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  mockEpisodesFor(chapter.id, [episode]);
  vi.mocked(queries.useBeatList).mockReturnValue({
    data: paginated(beats),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  mockTransitionsFor(episode.id, []);

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

async function expandEpisode(user: ReturnType<typeof userEvent.setup>) {
  // Chapter row starts expanded; expand the episode row to reveal transitions.
  const episodeRow = await screen.findByTestId('episode-row-author');
  const toggle = within(episodeRow).getByRole('button', { name: new RegExp(episode.title) });
  await user.click(toggle);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryAuthorTree - routing rules (#3563)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a transition rule under the target line once the episode is expanded', async () => {
    const user = userEvent.setup();
    setup();
    mockTransitionsFor(episode.id, [
      {
        ...transition,
        required_outcomes: [
          {
            id: 1,
            beat: 4,
            beat_title: 'Hostage exchange',
            required_outcome: 'failure',
            required_outcome_key: '',
            stake: null,
            stake_summary: '',
            required_stake_column: '',
          },
        ],
      },
    ]);

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const rule = await screen.findByTestId('transition-rule-text');
    expect(rule).toHaveTextContent('Hostage exchange = FAILURE');
    expect(rule.getAttribute('title')).toBe('Hostage exchange = FAILURE');
  });

  it('says "Always eligible" for a transition without rules', async () => {
    const user = userEvent.setup();
    setup();
    mockTransitionsFor(episode.id, [{ ...transition, required_outcomes: [] }]);

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    expect(await screen.findByTestId('transition-rule-text')).toHaveTextContent('Always eligible');
  });

  it('marks an episode row that has routing problems', () => {
    setup();
    mockEpisodesFor(chapter.id, [
      { ...episode, routing_problems: ['beat #4 = FAILURE: no transition accepts it'] },
    ]);

    renderWithProviders(<StoryAuthorTree story={story} />);

    const badge = screen.getByTestId('episode-routing-warning');
    expect(badge).toHaveTextContent('1 routing problem');
    expect(badge.getAttribute('title')).toContain('no transition accepts it');
  });

  it('shows no marker for a clean episode', () => {
    setup();
    mockEpisodesFor(chapter.id, [{ ...episode, routing_problems: [] }]);

    renderWithProviders(<StoryAuthorTree story={story} />);

    expect(screen.queryByTestId('episode-routing-warning')).not.toBeInTheDocument();
  });
});
