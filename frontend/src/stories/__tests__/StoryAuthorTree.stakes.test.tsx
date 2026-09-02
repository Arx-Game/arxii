/**
 * StoryAuthorTree "Stakes" chevron wiring tests (#3561 fold-in).
 *
 * BeatRowAuthor gained a "Stakes" chevron that toggles a `StakesPanel`
 * mount under the beat row, default collapsed. StakesPanel has its own
 * suite (`__tests__/stakes/StakesPanel.test.tsx`); this file only asserts
 * the WIRING - collapsed by default, mounts on click - mirroring the F2
 * (StoryAuthorTree.runcontrol) harness: mock `../queries` via importOriginal
 * so every hook the tree + mounted CRUD dialogs touch is controllable, and
 * stub `StakesPanel` itself so this file doesn't need its whole query
 * surface (useStakes/useStakeTemplates/useCreateStake/useGMProfileMine/...).
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StoryAuthorTree } from '../components/StoryAuthorTree';
import type { Beat, ChapterList, EpisodeList, Story } from '../types';

// ---------------------------------------------------------------------------
// Mocks
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
  };
});

vi.mock('../components/stakes/StakesPanel', () => ({
  StakesPanel: ({ beat }: { beat: Beat }) => (
    <div data-testid="stub-stakes-panel">stakes panel for beat {beat.id}</div>
  ),
}));

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
    can_mark: false,
    ...overrides,
  } as Beat;
}

// ---------------------------------------------------------------------------
// Mock harness
// ---------------------------------------------------------------------------

interface SetupOptions {
  beats?: Beat[];
}

function paginated<T>(results: T[]) {
  return { count: results.length, results, next: null, previous: null };
}

const noopMutation = {
  mutate: vi.fn(),
  isPending: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

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
}

async function expandEpisode(user: ReturnType<typeof userEvent.setup>) {
  const episodeRow = await screen.findByTestId('episode-row-author');
  const toggle = within(episodeRow).getByRole('button', { name: /the reckoning/i });
  await user.click(toggle);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryAuthorTree "Stakes" chevron wiring (#3561)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('is collapsed by default - the StakesPanel stub is not rendered', async () => {
    const user = userEvent.setup();
    setup();

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    expect(within(beatRow).getByTestId('beat-stakes-toggle')).toBeInTheDocument();
    expect(within(beatRow).queryByTestId('stub-stakes-panel')).not.toBeInTheDocument();
  });

  it('renders the StakesPanel stub for the right beat after clicking the chevron', async () => {
    const user = userEvent.setup();
    setup({ beats: [makeBeat({ id: 321 })] });

    renderWithProviders(<StoryAuthorTree story={story} />);
    await expandEpisode(user);

    const beatRow = await screen.findByTestId('beat-row-author');
    await user.click(within(beatRow).getByTestId('beat-stakes-toggle'));

    expect(within(beatRow).getByTestId('stub-stakes-panel')).toHaveTextContent(
      'stakes panel for beat 321'
    );
  });
});
