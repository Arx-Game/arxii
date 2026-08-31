/**
 * OffscreenActsPlate tests (#3412 slice 3, tasks 4/5) — renders only for a
 * docked character, links to the journal/goals surfaces, never renders a
 * proclamation row (no FE compose surface exists — see the component's doc
 * comment), and (task 5) branches on `lifecycle_state`: ALIVE/COMA keep the
 * act rows, CAPTURED/DEAD/RETIRED/UNKNOWN show world-voice refusal prose
 * instead.
 */
import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { OffscreenActsPlate } from '../OffscreenActsPlate';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { hydrateActiveCharacter, resetGame } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
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

describe('OffscreenActsPlate', () => {
  afterEach(() => {
    store.dispatch(resetGame());
  });

  it('renders nothing when no character is docked', () => {
    renderWithProviders(<OffscreenActsPlate characters={[aria, bianca]} />);
    expect(screen.queryByText('Offscreen Acts')).not.toBeInTheDocument();
  });

  it('renders nothing when the docked entry id is not in the characters list (stale selection)', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 999 }));
    renderWithProviders(<OffscreenActsPlate characters={[aria, bianca]} />);
    expect(screen.queryByText('Offscreen Acts')).not.toBeInTheDocument();
  });

  it('renders the plate with journal and goals rows for the docked character', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<OffscreenActsPlate characters={[aria, bianca]} />);

    expect(screen.getByText('Offscreen Acts')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Write in your journal' })).toHaveAttribute(
      'href',
      '/journals'
    );
    expect(screen.getByRole('link', { name: 'Set your goals' })).toHaveAttribute(
      'href',
      '/xp-kudos'
    );
  });

  it('never renders a proclamation row (no FE compose surface exists)', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<OffscreenActsPlate characters={[aria]} />);

    expect(screen.queryByText(/proclaim/i)).not.toBeInTheDocument();
  });

  it('does not duplicate persona switching (that lives on PersonaTiles/CharactersBand)', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<OffscreenActsPlate characters={[aria]} />);

    expect(screen.queryByRole('tablist', { name: 'Personas' })).not.toBeInTheDocument();
  });

  it('renders the act rows for a COMA docked character (the unwritten fall-through state)', () => {
    const inComa = { ...aria, lifecycle_state: 'COMA' };
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<OffscreenActsPlate characters={[inComa]} />);

    expect(screen.getByRole('link', { name: 'Write in your journal' })).toBeInTheDocument();
  });

  it.each([
    ['CAPTURED', /smuggled out/i],
    ['DEAD', /séance/i],
    ['RETIRED', /stepped away/i],
    ['UNKNOWN', /whereabouts are unknown/i],
  ])(
    'renders world-voice refusal prose instead of the act rows for %s',
    (lifecycle_state, expectedText) => {
      const degraded = { ...aria, lifecycle_state };
      store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
      renderWithProviders(<OffscreenActsPlate characters={[degraded]} />);

      expect(screen.getByText(expectedText)).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Write in your journal' })).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Set your goals' })).not.toBeInTheDocument();
    }
  );
});
