/**
 * CharactersBand tests (#3412 slice 2) — the Hall's "Your Characters" band.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CharactersBand } from '../CharactersBand';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setBrowsingIdentity, resetGame } from '@/store/gameSlice';
import { readTabIdentity } from '@/store/browsingIdentity';
import type { MyRosterEntry } from '@/roster/types';

const mockSelectMutate = vi.fn();
vi.mock('@/roster/queries', () => ({
  useSelectCharacterMutation: () => ({ mutate: mockSelectMutate, isPending: false }),
  // useBrowsingIdentity() calls this internally; CharactersBand only reads
  // `entryId` off the hook (not `entry`/`name`), so an empty roster here is
  // fine: the docked-highlight comparison is id-to-id straight off Redux.
  useMyRosterEntriesQuery: () => ({ data: [] }),
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
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

describe('CharactersBand', () => {
  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
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
    store.dispatch(setBrowsingIdentity(1));
    renderWithProviders(<CharactersBand characters={[aria, bianca]} />);

    expect(screen.getByText('Playing: Currently Offscreen')).toBeInTheDocument();
  });

  it('shows no offscreen meta on an undocked card', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    expect(screen.queryByText('Playing: Currently Offscreen')).not.toBeInTheDocument();
  });

  it('shows "Currently Offscreen" for a docked ALIVE character', () => {
    store.dispatch(setBrowsingIdentity(1));
    renderWithProviders(<CharactersBand characters={[aria]} />);

    expect(screen.getByText('Playing: Currently Offscreen')).toBeInTheDocument();
  });

  it('shows a degraded state label instead of "Currently Offscreen" for a docked CAPTURED character (#3412 review IMPORTANT-1)', () => {
    const captured: MyRosterEntry = { ...aria, lifecycle_state: 'CAPTURED' };
    store.dispatch(setBrowsingIdentity(1));
    renderWithProviders(<CharactersBand characters={[captured]} />);

    expect(screen.getByText('Playing: Held captive')).toBeInTheDocument();
    expect(screen.queryByText('Playing: Currently Offscreen')).not.toBeInTheDocument();
  });

  it.each([
    ['DEAD', 'Dead'],
    ['RETIRED', 'Retired'],
    ['UNKNOWN', 'Whereabouts unknown'],
  ])('shows the "%s" state label for a docked %s character', (lifecycleState, label) => {
    const entry: MyRosterEntry = { ...aria, lifecycle_state: lifecycleState };
    store.dispatch(setBrowsingIdentity(1));
    renderWithProviders(<CharactersBand characters={[entry]} />);

    expect(screen.getByText(`Playing: ${label}`)).toBeInTheDocument();
  });

  it('selecting a card dispatches the local hydrate and fires the select mutation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CharactersBand characters={[aria]} />);

    await user.click(screen.getByText('Aria'));

    expect(mockSelectMutate).toHaveBeenCalledWith(1);
    expect(store.getState().game.activeEntryId).toBe(1);
    expect(store.getState().game.active).toBe('Aria');
    // #3479: the picking tab's own browsing identity updates immediately,
    // independent of the select mutation's account-wide round trip.
    expect(store.getState().game.browsingEntryId).toBe(1);
    expect(readTabIdentity()?.entryId).toBe(1);
  });

  it('"Clear Active Character" is disabled when nothing is docked', () => {
    renderWithProviders(<CharactersBand characters={[aria]} />);
    expect(screen.getByRole('button', { name: 'Clear Active Character' })).toBeDisabled();
  });

  it('"Clear Active Character" clears the docked selection when clicked', async () => {
    const user = userEvent.setup();
    store.dispatch(setBrowsingIdentity(1));
    renderWithProviders(<CharactersBand characters={[aria]} />);

    const clearButton = screen.getByRole('button', { name: 'Clear Active Character' });
    expect(clearButton).not.toBeDisabled();

    await user.click(clearButton);

    expect(mockSelectMutate).toHaveBeenCalledWith(null);
    expect(store.getState().game.activeEntryId).toBeNull();
    expect(store.getState().game.browsingEntryId).toBeNull();
    expect(readTabIdentity()).toBeNull();
  });
});
