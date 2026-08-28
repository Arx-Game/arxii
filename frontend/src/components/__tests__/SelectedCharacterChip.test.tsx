/**
 * SelectedCharacterChip (#3412) — the docked-portrait chip's own contract in
 * isolation: portrait/name render, the real `PersonaSwitcher` works from this
 * mount point (not just inside `/game`'s `GameTopBar`), and "Enter the world"
 * links to `/game`. The chip deliberately has NO clear-selection control
 * (Apostate ruling 2026-08-28 — "step away" read as logout; "Clear Active
 * Character" lands in the Hall's "Your Characters" band in slice 2).
 *
 * `PersonaSwitcher`'s OWN underlying queries (`@/game/personaQueries`) are
 * mocked here — same technique as `PersonaSwitcher.test.tsx` — so this test
 * exercises the real switcher component end to end from the chip, proving
 * it isn't coupled to `GameTopBar`/`/game` in any way.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { SwitchablePersona } from '@/game/personaQueries';
import { SelectedCharacterChip } from '../SelectedCharacterChip';
import type { MyRosterEntry } from '@/roster/types';

const { state, setActiveMutate, selectMutate } = vi.hoisted(() => ({
  state: { personas: [] as SwitchablePersona[] },
  setActiveMutate: vi.fn(),
  selectMutate: vi.fn(),
}));

vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: state.personas }),
  useSetActivePersonaMutation: () => ({ mutate: setActiveMutate, isPending: false }),
  useSetPersonaProfileMutation: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('@/roster/queries', () => ({
  useSelectCharacterMutation: () => ({ mutate: selectMutate, isPending: false }),
}));

function persona(
  id: number,
  name: string,
  type: SwitchablePersona['persona_type']
): SwitchablePersona {
  return {
    id,
    name,
    persona_type: type,
    is_fake_name: type === 'temporary',
    thumbnail_url: null,
    thumbnail_media_url: null,
    guise_concept: '',
    guise_quote: '',
    guise_personality: '',
    guise_background: '',
  };
}

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
};

describe('SelectedCharacterChip (#3412)', () => {
  it('renders the portrait, name, and an Enter-the-world link to /game', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <MemoryRouter>
        <SelectedCharacterChip entry={aria} />
      </MemoryRouter>
    );

    // "Aria" legitimately appears twice: the chip's own name span, and
    // PersonaSwitcher's single-persona fallback (no switcher UI, just the
    // worn persona's name) — the primary persona here shares the character's
    // name, same as most characters' own primary face.
    expect(screen.getAllByText('Aria')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /enter the world/i })).toHaveAttribute('href', '/game');
  });

  it('lets the player switch which face the character presents as, from this mount point', async () => {
    // Two faces — PersonaSwitcher renders the actual switching dropdown
    // (single-face collapses to a bare name, per PersonaSwitcher.test.tsx).
    state.personas = [persona(7, 'Aria', 'primary'), persona(8, 'The Veiled Lady', 'established')];
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <SelectedCharacterChip entry={{ ...aria, active_persona_id: 7 }} />
      </MemoryRouter>
    );

    await user.click(screen.getByTitle('Switch which identity you are presenting as'));
    await user.click(screen.getByText('The Veiled Lady'));

    expect(setActiveMutate).toHaveBeenCalledWith(8);
  });

  it('shows the offscreen state label off /game, and drops it while in the world', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    const { unmount } = render(
      <MemoryRouter initialEntries={['/tidings']}>
        <SelectedCharacterChip entry={aria} />
      </MemoryRouter>
    );
    expect(screen.getByText(/Playing: Currently Offscreen/)).toBeInTheDocument();
    unmount();

    // On /game the player IS in the world — the chip must not assert an
    // offscreen fact there; only the worn-persona line remains.
    render(
      <MemoryRouter initialEntries={['/game']}>
        <SelectedCharacterChip entry={aria} />
      </MemoryRouter>
    );
    expect(screen.queryByText(/Playing: Currently Offscreen/)).not.toBeInTheDocument();
    expect(screen.getByText(/as Aria/)).toBeInTheDocument();
  });

  it('carries no clear-selection control (ruled: clearing lives with the character list)', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <MemoryRouter>
        <SelectedCharacterChip entry={aria} />
      </MemoryRouter>
    );

    expect(screen.queryByTitle('Step away')).not.toBeInTheDocument();
    expect(selectMutate).not.toHaveBeenCalled();
  });
});
