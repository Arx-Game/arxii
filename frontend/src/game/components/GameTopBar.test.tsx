import { screen, within } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';

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

const rosterEntry: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
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
  afterEach(() => {
    store.dispatch(resetGame());
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
});
