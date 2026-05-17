/**
 * ProgressStateBanner Tests — Task F1
 *
 * Thin read-only banner on the StoryAuthorPage selected-story pane giving the
 * GM at-a-glance context for where the assigned PC/group currently is and
 * whether the story is paused waiting on the GM, so on-the-fly authoring is
 * informed (the "nimble in-session" requirement).
 *
 * DATA SOURCE (minimal existing, no backend added):
 *   useMyActiveStories() — the GET /api/stories/my-active/ dashboard. It is the
 *   only existing FE source that yields, per story, BOTH the current episode
 *   (current_episode_title) AND a human-readable status (status / status_label)
 *   AND scope, keyed by story_id across the three scope arrays. The generated
 *   GroupStoryProgress/GlobalStoryProgress schemas expose only current_episode
 *   (id) + is_active + timestamps — no status — and there is no CHARACTER-scope
 *   progress ViewSet, so the dashboard is the minimal existing source. The
 *   backbone ProgressStatus literal (active/waiting_for_gm/resting/completed)
 *   is not exposed to the FE; the dashboard's StoryEpisodeStatus value is the
 *   available analogue and `on_hold` (frontier / GM-must-author-next) is the
 *   practical "waiting for GM / resting" pause an author needs flagged.
 *
 * Covers:
 *  - active position: shows the current episode title + status, with active
 *    emphasis for a running episode (ready_to_resolve)
 *  - the GM-attention pause (on_hold — frontier, GM must author next) renders
 *    with distinct attention copy/treatment vs an active episode
 *  - a muted pause (scheduled) renders distinctly (muted, not attention)
 *  - current_episode null → "At frontier" (no episode authored yet)
 *  - no matching dashboard entry (UNASSIGNED / not running) → calm
 *    "Not yet running" line, NOT an error
 *  - loading state while the dashboard query is pending
 *
 * Mirrors the GMNotesPanel / PromoteMaturityButton harness: mock `../queries`
 * so useMyActiveStories returns controllable data / loading variants.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ProgressStateBanner } from '../components/ProgressStateBanner';
import type { MyActiveStoryEntry, MyActiveStoriesResponse } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useMyActiveStories: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEntry(overrides: Partial<MyActiveStoryEntry> = {}): MyActiveStoryEntry {
  return {
    story_id: 3,
    story_title: 'The Hollow Crown',
    scope: 'character',
    current_episode_id: 11,
    current_episode_title: 'The Gathering Storm',
    chapter_title: 'Act I',
    status: 'ready_to_resolve',
    status_label: 'Ready to resolve (auto-advance possible)',
    chapter_order: 1,
    episode_order: 1,
    open_session_request_id: null,
    scheduled_event_id: null,
    scheduled_real_time: null,
    ...overrides,
  };
}

function mockDashboard(
  state: 'loading' | 'data',
  response?: Partial<MyActiveStoriesResponse>
): void {
  if (state === 'loading') {
    vi.mocked(queries.useMyActiveStories).mockReturnValue({
      data: undefined,
      isLoading: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    return;
  }
  vi.mocked(queries.useMyActiveStories).mockReturnValue({
    data: {
      character_stories: [],
      group_stories: [],
      global_stories: [],
      ...response,
    },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ProgressStateBanner — Task F1', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the current episode and an active status for a running episode', () => {
    mockDashboard('data', { character_stories: [makeEntry()] });

    renderWithProviders(<ProgressStateBanner storyId={3} scope="character" />);

    expect(screen.getByTestId('progress-state-banner')).toBeInTheDocument();
    expect(screen.getByText('The Gathering Storm')).toBeInTheDocument();
    // Human-readable status from the backend label.
    expect(screen.getByTestId('progress-state-status')).toHaveTextContent(/ready to resolve/i);
    // Active running episode → active treatment, not the attention pause.
    expect(screen.getByTestId('progress-state-banner')).toHaveAttribute('data-state', 'active');
  });

  it('renders the GM-attention pause (on_hold / frontier) with distinct attention copy', () => {
    mockDashboard('data', {
      character_stories: [
        makeEntry({
          status: 'on_hold',
          status_label: 'On hold (frontier — unauthored next)',
          current_episode_id: 12,
          current_episode_title: 'A Quiet Interlude',
        }),
      ],
    });

    renderWithProviders(<ProgressStateBanner storyId={3} scope="character" />);

    const banner = screen.getByTestId('progress-state-banner');
    expect(banner).toHaveAttribute('data-state', 'attention');
    expect(screen.getByTestId('progress-state-status')).toHaveTextContent(/waiting for gm/i);
    expect(screen.getByText('A Quiet Interlude')).toBeInTheDocument();
  });

  it('renders a muted pause (scheduled) distinctly from the attention state', () => {
    mockDashboard('data', {
      group_stories: [
        makeEntry({
          scope: 'group',
          status: 'scheduled',
          status_label: 'GM session scheduled',
          current_episode_title: 'The Council Meets',
        }),
      ],
    });

    renderWithProviders(<ProgressStateBanner storyId={3} scope="group" />);

    const banner = screen.getByTestId('progress-state-banner');
    expect(banner).toHaveAttribute('data-state', 'muted');
    expect(screen.getByTestId('progress-state-status')).toHaveTextContent(/scheduled/i);
  });

  it('shows "At frontier" when current_episode is null', () => {
    mockDashboard('data', {
      character_stories: [
        makeEntry({
          status: 'on_hold',
          status_label: 'On hold (frontier — unauthored next)',
          current_episode_id: null,
          current_episode_title: null,
        }),
      ],
    });

    renderWithProviders(<ProgressStateBanner storyId={3} scope="character" />);

    expect(screen.getByTestId('progress-state-episode')).toHaveTextContent(/at frontier/i);
  });

  it('renders a calm "Not yet running" line when there is no matching progress', () => {
    // Dashboard returns entries for other stories only — none for storyId 3.
    mockDashboard('data', {
      character_stories: [makeEntry({ story_id: 99 })],
    });

    renderWithProviders(<ProgressStateBanner storyId={3} scope="character" />);

    const banner = screen.getByTestId('progress-state-banner');
    expect(banner).toHaveAttribute('data-state', 'idle');
    expect(screen.getByTestId('progress-state-idle')).toHaveTextContent(/not yet running/i);
    // Calm, not an error.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a loading state while the dashboard query is pending', () => {
    mockDashboard('loading');

    renderWithProviders(<ProgressStateBanner storyId={3} scope="character" />);

    expect(screen.getByTestId('progress-state-loading')).toBeInTheDocument();
  });
});
