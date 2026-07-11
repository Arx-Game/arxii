import { screen } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';

import { GameTopBar } from './GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { resetGame } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

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
});
