/**
 * CharactersBand tests (#3412 slice 2) — the Hall's "Your Characters" band.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CharactersBand } from '../CharactersBand';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { hydrateActiveCharacter, resetGame } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const mockSelectMutate = vi.fn();
vi.mock('@/roster/queries', () => ({
  useSelectCharacterMutation: () => ({ mutate: mockSelectMutate, isPending: false }),
}));

vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: [] }),
  useSetActivePersonaMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 4,
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
};

describe('CharactersBand', () => {
  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('renders the band title', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    expect(screen.getByText('Your Characters')).toBeInTheDocument();
  });

  it('shows the tidings CountChip with the correct accessible title', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    const chip = screen.getByTitle('4 tidings waiting');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('aria-label', '4 tidings waiting');
  });

  it('renders no CountChip for a character with zero unread tidings', () => {
    renderWithProviders(<CharactersBand characters={[bianca]} />);
    expect(screen.queryByTitle(/tidings waiting/)).not.toBeInTheDocument();
  });

  it('marks the docked card distinct and shows the offscreen meta line', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<CharactersBand characters={[aria, bianca]} />);

    expect(screen.getByText('Playing: Currently Offscreen')).toBeInTheDocument();
  });

  it('shows no offscreen meta on an undocked card', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    expect(screen.queryByText('Playing: Currently Offscreen')).not.toBeInTheDocument();
  });

  it('selecting a card dispatches the local hydrate and fires the select mutation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CharactersBand characters={[aria]} />);

    await user.click(screen.getByText('Aria'));

    expect(mockSelectMutate).toHaveBeenCalledWith(1);
    expect(store.getState().game.activeEntryId).toBe(1);
    expect(store.getState().game.active).toBe('Aria');
  });

  it('"Clear Active Character" is disabled when nothing is docked', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    expect(screen.getByRole('button', { name: 'Clear Active Character' })).toBeDisabled();
  });

  it('"Clear Active Character" clears the docked selection when clicked', async () => {
    const user = userEvent.setup();
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<CharactersBand characters={[aria]} />);

    const clearButton = screen.getByRole('button', { name: 'Clear Active Character' });
    expect(clearButton).not.toBeDisabled();

    await user.click(clearButton);

    expect(mockSelectMutate).toHaveBeenCalledWith(null);
    expect(store.getState().game.activeEntryId).toBeNull();
  });
});
