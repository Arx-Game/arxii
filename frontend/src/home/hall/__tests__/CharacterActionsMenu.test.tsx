/**
 * CharacterActionsMenu tests (#3996) — the card's overflow menu picks its one
 * action from provenance and frozen state.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CharacterActionsMenu } from '../CharacterActionsMenu';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { MyRosterEntry } from '@/roster/types';

const mockFreeze = vi.fn();
const mockThaw = vi.fn();
const mockGiveUp = vi.fn();
vi.mock('@/roster/queries', () => ({
  useFreezeEntryMutation: () => ({ mutate: mockFreeze, isPending: false }),
  useThawEntryMutation: () => ({ mutate: mockThaw, isPending: false }),
  useGiveUpEntryMutation: () => ({ mutate: mockGiveUp, isPending: false }),
}));

function entry(overrides: Partial<MyRosterEntry>): MyRosterEntry {
  return {
    id: 1,
    name: 'Aria',
    character_id: 41,
    profile_picture_url: null,
    primary_persona_id: null,
    active_persona_id: null,
    unread_narrative_count: 0,
    unread_direct: 0,
    has_ambient_unread: false,
    attention_as_of_id: 0,
    lifecycle_state: 'ALIVE',
    roster_type: 'Active',
    character_type: 'PC',
    activity_state: 'ACTIVE',
    activity_requirement: 'NONE',
    creation_provenance: 'PLAYER',
    thaw_available_at: null,
    ...overrides,
  };
}

async function openMenu(name = 'Aria') {
  // Radix leaves `pointer-events: none` on the body while a menu or dialog is
  // open; the check would fail the tests that follow the first in this file.
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  await user.click(screen.getByRole('button', { name: `Actions for ${name}` }));
  return user;
}

describe('CharacterActionsMenu', () => {
  afterEach(() => vi.clearAllMocks());

  it('offers Freeze for an original character and runs it after confirming', async () => {
    renderWithProviders(<CharacterActionsMenu entry={entry({})} />);
    const user = await openMenu();
    await user.click(screen.getByRole('menuitem', { name: 'Freeze' }));
    expect(screen.getByText('Freeze Aria?')).toBeInTheDocument();
    await user.click(screen.getByTestId('slot-action-confirm'));
    expect(mockFreeze).toHaveBeenCalledWith(1, expect.anything());
  });

  it('offers Give up for a roster character', async () => {
    renderWithProviders(
      <CharacterActionsMenu entry={entry({ creation_provenance: 'STAFF', name: 'Bram' })} />
    );
    await openMenu('Bram');
    expect(screen.getByRole('menuitem', { name: 'Give up' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Freeze' })).not.toBeInTheDocument();
  });

  it('offers Thaw for a frozen original character once the date has passed', async () => {
    const past = new Date(Date.now() - 86400000).toISOString();
    renderWithProviders(
      <CharacterActionsMenu entry={entry({ activity_state: 'FROZEN', thaw_available_at: past })} />
    );
    const user = await openMenu();
    await user.click(screen.getByRole('menuitem', { name: 'Thaw' }));
    await user.click(screen.getByTestId('slot-action-confirm'));
    expect(mockThaw).toHaveBeenCalledWith(1, expect.anything());
  });

  it('disables Thaw until the thaw date', async () => {
    const future = new Date(Date.now() + 10 * 86400000).toISOString();
    renderWithProviders(
      <CharacterActionsMenu
        entry={entry({ activity_state: 'FROZEN', thaw_available_at: future })}
      />
    );
    await openMenu();
    const item = screen.getByRole('menuitem', { name: /Thaw from/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
  });
});
