/**
 * StoryDetailPage Tests
 *
 * Tests rendering the story header, episode panel, and story log.
 */

import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StoryDetailPage } from '../pages/StoryDetailPage';

// Mock narrative queries used by MuteStoryToggle
vi.mock('../../narrative/queries', () => ({
  useStoryMutes: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
    isSuccess: true,
    error: null,
  })),
  useMuteStory: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useUnmuteStory: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

const makeMutationIdle = () => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isSuccess: false,
  isError: false,
  isIdle: true,
  error: null,
  data: undefined,
  variables: undefined,
  status: 'idle' as const,
  reset: vi.fn(),
  context: undefined,
  failureCount: 0,
  failureReason: null,
  isPaused: false,
  submittedAt: 0,
});

vi.mock('../queries', () => ({
  useStory: vi.fn(),
  useMyActiveStories: vi.fn(),
  useEpisode: vi.fn(),
  useBeatList: vi.fn(),
  useAggregateBeatContributions: vi.fn(),
  useStoryLog: vi.fn(),
  useSessionRequest: vi.fn(),
  useContributeToBeat: vi.fn(),
  // Required by BeatRow → MarkBeatDialog for gm_marked beats (Wave 6)
  useMarkBeat: vi.fn(),
  // Wave 5: ChangeMyGMDialog hooks
  useDetachStoryFromTable: vi.fn(),
  useOfferStoryToGM: vi.fn(),
  useGMProfiles: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockStory = {
  id: 1,
  title: 'A Knights Tale',
  description: 'A personal story of growth.',
  status: 'active',
  privacy: 'private',
  scope: 'character',
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 42,
  chapters_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  completed_at: null,
  primary_table: null,
};

const mockActiveEntry = {
  story_id: 1,
  story_title: 'A Knights Tale',
  scope: 'character',
  current_episode_id: 10,
  current_episode_title: 'The Journey',
  chapter_title: 'Chapter One',
  status: 'waiting_on_beats',
  status_label: 'Waiting on beats',
  chapter_order: 1,
  episode_order: 2,
  open_session_request_id: null,
  scheduled_event_id: null,
  scheduled_real_time: null,
};

const mockEpisode = {
  id: 10,
  chapter: 1,
  title: 'The Journey',
  description: 'The hero begins.',
  order: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

const mockBeat = {
  id: 100,
  episode: 10,
  predicate_type: 'gm_marked',
  outcome: 'unsatisfied',
  visibility: 'hinted',
  internal_description: 'GM internal view',
  player_hint: 'Find the lost sword',
  player_resolution_text: null,
  order: 1,
  required_level: null,
  required_achievement: null,
  required_condition_template: null,
  required_codex_entry: null,
  referenced_story: null,
  referenced_milestone_type: null,
  referenced_chapter: null,
  referenced_episode: null,
  required_points: null,
  agm_eligible: false,
  deadline: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

function setupMocks(
  opts: {
    storyLoading?: boolean;
    beatOutcome?: string;
  } = {}
) {
  const beat = { ...mockBeat, outcome: opts.beatOutcome ?? 'unsatisfied' };

  vi.mocked(queries.useStory).mockReturnValue({
    data: opts.storyLoading ? undefined : mockStory,
    isLoading: opts.storyLoading ?? false,
    isSuccess: !opts.storyLoading,
    error: null,
  } as unknown as ReturnType<typeof queries.useStory>);

  vi.mocked(queries.useMyActiveStories).mockReturnValue({
    data: {
      character_stories: [mockActiveEntry],
      group_stories: [],
      global_stories: [],
    },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useMyActiveStories>);

  vi.mocked(queries.useEpisode).mockReturnValue({
    data: mockEpisode,
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useEpisode>);

  vi.mocked(queries.useBeatList).mockReturnValue({
    data: { count: 1, next: null, previous: null, results: [beat] },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useBeatList>);

  vi.mocked(queries.useAggregateBeatContributions).mockReturnValue({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useAggregateBeatContributions>);

  vi.mocked(queries.useStoryLog).mockReturnValue({
    data: { entries: [] },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryLog>);

  vi.mocked(queries.useSessionRequest).mockReturnValue({
    data: undefined,
    isLoading: false,
    isSuccess: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useSessionRequest>);

  vi.mocked(queries.useContributeToBeat).mockReturnValue({
    mutate: vi.fn(),
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
  } as unknown as ReturnType<typeof queries.useContributeToBeat>);

  vi.mocked(queries.useMarkBeat).mockReturnValue({
    mutate: vi.fn(),
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
  } as unknown as ReturnType<typeof queries.useMarkBeat>);

  // Wave 5: ChangeMyGMDialog hooks
  vi.mocked(queries.useDetachStoryFromTable).mockReturnValue(
    makeMutationIdle() as unknown as ReturnType<typeof queries.useDetachStoryFromTable>
  );
  vi.mocked(queries.useOfferStoryToGM).mockReturnValue(
    makeMutationIdle() as unknown as ReturnType<typeof queries.useOfferStoryToGM>
  );
  vi.mocked(queries.useGMProfiles).mockReturnValue({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useGMProfiles>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders story title and scope badge', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.getByText('A Knights Tale')).toBeInTheDocument();
    expect(screen.getByText('Personal')).toBeInTheDocument();
  });

  it('renders status label from active entry', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.getByText('Waiting on beats')).toBeInTheDocument();
  });

  it('renders current episode section', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.getByText('Current Episode')).toBeInTheDocument();
    expect(screen.getByText('The Journey')).toBeInTheDocument();
  });

  it('renders beat with player_hint', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.getByText('Find the lost sword')).toBeInTheDocument();
  });

  it('renders Story Log section header', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.getByText('Story Log')).toBeInTheDocument();
  });

  it('shows "Offer to a GM" CTA for CHARACTER-scope owned story seeking a GM', () => {
    setupMocks();
    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    // mockStory has scope='character', primary_table=null, and is in character_stories
    expect(screen.getByTestId('change-gm-button')).toBeInTheDocument();
    expect(screen.getByTestId('change-gm-button')).toHaveTextContent('Offer to a GM');
  });

  it('does not show CTA for GROUP-scope story', () => {
    // Override useStory to return a group-scope story
    vi.mocked(queries.useStory).mockReturnValue({
      data: { ...mockStory, scope: 'group' },
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof queries.useStory>);

    vi.mocked(queries.useMyActiveStories).mockReturnValue({
      data: {
        character_stories: [], // not in character_stories
        group_stories: [{ ...mockActiveEntry, story_id: 1 }],
        global_stories: [],
      },
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof queries.useMyActiveStories>);

    renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    expect(screen.queryByTestId('change-gm-button')).not.toBeInTheDocument();
  });

  it('shows loading skeleton when story is loading', () => {
    setupMocks({ storyLoading: true });
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/stories/:id" element={<StoryDetailPage />} />
      </Routes>,
      { initialEntries: ['/stories/1'] }
    );

    // Skeletons rendered during loading
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });
});

// Beat outcome state tests
describe('BeatRow outcome states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const OUTCOMES: Array<{ outcome: string; label: string }> = [
    { outcome: 'unsatisfied', label: 'Unsatisfied' },
    { outcome: 'success', label: 'Success' },
    { outcome: 'failure', label: 'Failure' },
    { outcome: 'expired', label: 'Expired' },
    { outcome: 'pending_gm_review', label: 'Pending Review' },
  ];

  for (const { outcome, label } of OUTCOMES) {
    it(`renders ${outcome} outcome badge`, () => {
      setupMocks({ beatOutcome: outcome });
      renderWithProviders(
        <Routes>
          <Route path="/stories/:id" element={<StoryDetailPage />} />
        </Routes>,
        { initialEntries: ['/stories/1'] }
      );

      expect(screen.getByText(label)).toBeInTheDocument();
    });
  }
});
