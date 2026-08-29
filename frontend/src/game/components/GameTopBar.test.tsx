import { screen, within } from '@testing-library/react';
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';

import { GameTopBar } from './GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import {
  resetGame,
  startSession,
  addSceneInteraction,
  addSessionMessage,
  setSceneBaseline,
} from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';
import type { InteractionWsPayload } from '@/hooks/types';

// GameTopBar reads `sessions`/`active` from Redux (via useAppSelector) and calls
// useGameSocket() — both are safe to exercise for real here, mirroring
// GamePage.test.tsx's "shows game interface when authenticated" case, which
// renders the same component tree without mocking either. WeatherWidget/
// ComfortWidget's queries are `enabled: false` when there's no active
// room/character, so no network calls fire.

// #3412 S4 — GameTopBar's ClockReadout reuses the Hall's useClockQuery
// directly (no relocation needed — see the import comment in GameTopBar.tsx),
// so the mock target is the Hall's queries module, mirroring WorldBand.test.tsx.
const mockUseClockQuery = vi.fn();
vi.mock('@/home/hall/queries', () => ({
  useClockQuery: () => mockUseClockQuery(),
}));

const rosterEntry: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
};

// A second, background puppet (#2166) — Aria stays active; Bianca's session
// carries whatever attention state each test sets up.
const rosterEntry2: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
};

function makeWhisperInteraction(
  overrides: Partial<InteractionWsPayload> = {}
): InteractionWsPayload {
  return {
    id: 1,
    persona: { id: 99, name: 'Other', thumbnail_url: '' },
    content: 'psst.',
    mode: 'whisper',
    timestamp: '2026-01-01T00:00:00Z',
    scene_id: 100,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [8],
    target_persona_ids: [],
    ...overrides,
  };
}

describe('GameTopBar', () => {
  beforeEach(() => {
    // Default: no clock resolved yet (loading/disabled) — matches
    // WeatherWidget's own hide-until-resolved default so unrelated tests
    // aren't tripped up by a stray clock readout.
    mockUseClockQuery.mockReturnValue({ data: undefined });
  });

  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('shows the "No characters yet" message with both links when the account has zero characters', () => {
    renderWithProviders(<GameTopBar characters={[]} />);

    expect(screen.getByText(/no characters yet/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /browse the roster/i })).toHaveAttribute(
      'href',
      '/roster'
    );
    expect(screen.getByRole('link', { name: /create one/i })).toHaveAttribute(
      'href',
      '/characters/create'
    );
  });

  it('does not show the "No characters yet" message once the account has a character', () => {
    renderWithProviders(<GameTopBar characters={[rosterEntry]} />);

    expect(screen.queryByText(/no characters yet/i)).not.toBeInTheDocument();
  });

  describe('background-session attention badge (#2166)', () => {
    function seedBackgroundBianca() {
      // Bianca's session is created first, then Aria's — startSession makes
      // the most-recently-started character active, so this leaves Aria
      // active and Bianca as a background alt session.
      store.dispatch(startSession('Bianca'));
      store.dispatch(startSession('Aria'));
    }

    it('badges a background session with an unseen whisper as a numeric direct count', () => {
      seedBackgroundBianca();
      store.dispatch(setSceneBaseline({ character: 'Bianca', baselineId: 0 }));
      store.dispatch(
        addSceneInteraction({ character: 'Bianca', interaction: makeWhisperInteraction() })
      );

      renderWithProviders(<GameTopBar characters={[rosterEntry, rosterEntry2]} />);

      const biancaButton = screen.getByTitle('Switch to Bianca');
      expect(within(biancaButton).getByText('1')).toBeInTheDocument();
    });

    it('shows a muted ambient dot for a background session with unread but no direct attention', () => {
      seedBackgroundBianca();
      store.dispatch(
        addSessionMessage({
          character: 'Bianca',
          message: { content: 'The room stirs.', timestamp: Date.now(), type: 'text' },
        })
      );

      renderWithProviders(<GameTopBar characters={[rosterEntry, rosterEntry2]} />);

      const biancaButton = screen.getByTitle('Switch to Bianca');
      expect(within(biancaButton).queryByText(/[0-9]/)).not.toBeInTheDocument();
      expect(biancaButton.querySelector('.bg-muted-foreground\\/60')).not.toBeNull();
    });

    it('renders no badge for a background session with no unread attention', () => {
      seedBackgroundBianca();

      renderWithProviders(<GameTopBar characters={[rosterEntry, rosterEntry2]} />);

      const biancaButton = screen.getByTitle('Switch to Bianca');
      expect(within(biancaButton).queryByText(/[0-9]/)).not.toBeInTheDocument();
      expect(biancaButton.querySelector('.bg-muted-foreground\\/60')).toBeNull();
      expect(biancaButton.querySelector('.bg-red-500')).toBeNull();
    });
  });

  describe('own-sheet link (#3412 S4)', () => {
    it('renders the sheet link for the active entry, pointing at its RosterEntry id in a new tab', () => {
      store.dispatch(startSession('Aria'));
      renderWithProviders(<GameTopBar characters={[rosterEntry]} />);

      const link = screen.getByRole('link', { name: 'Your character sheet' });
      expect(link).toHaveAttribute('href', '/characters/1');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener');
    });

    it('omits the sheet link when there is no active entry', () => {
      renderWithProviders(<GameTopBar characters={[rosterEntry]} />);

      expect(screen.queryByRole('link', { name: 'Your character sheet' })).not.toBeInTheDocument();
    });
  });

  describe('clock readout (#3412 S4)', () => {
    it('renders season only (WeatherWidget already shows hh:mm), full date/time/phase in the title tooltip', () => {
      mockUseClockQuery.mockReturnValue({
        data: {
          ic_datetime: '2026-08-20T12:00:00Z',
          year: 1247,
          month: 3,
          day: 12,
          hour: 14,
          minute: 5,
          phase: 'day',
          season: 'summer',
          light_level: 1,
          paused: false,
        },
      });
      renderWithProviders(<GameTopBar characters={[]} />);

      const readout = screen.getByLabelText('The world clock');
      expect(readout).toHaveTextContent('Summer');
      expect(readout).not.toHaveTextContent('14:05');
      expect(readout).toHaveAttribute('title', 'Year 1247, Month 3, Day 12, 14:05 — Day');
      expect(screen.queryByText('(Paused)')).not.toBeInTheDocument();
    });

    it('shows a paused indicator when the clock is paused', () => {
      mockUseClockQuery.mockReturnValue({
        data: {
          ic_datetime: '2026-08-20T12:00:00Z',
          year: 1247,
          month: 3,
          day: 12,
          hour: 14,
          minute: 5,
          phase: 'day',
          season: 'summer',
          light_level: 1,
          paused: true,
        },
      });
      renderWithProviders(<GameTopBar characters={[]} />);

      expect(screen.getByText('(Paused)')).toBeInTheDocument();
    });

    it('hides entirely while loading (no layout jump)', () => {
      mockUseClockQuery.mockReturnValue({ data: undefined });
      renderWithProviders(<GameTopBar characters={[]} />);

      expect(screen.queryByLabelText('The world clock')).not.toBeInTheDocument();
    });

    it('hides entirely on error — no throwOnError, data resolves undefined', () => {
      mockUseClockQuery.mockReturnValue({ data: undefined, isError: true });
      renderWithProviders(<GameTopBar characters={[]} />);

      expect(screen.queryByLabelText('The world clock')).not.toBeInTheDocument();
    });
  });
});
