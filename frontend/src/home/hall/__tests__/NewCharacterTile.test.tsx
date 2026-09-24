/**
 * NewCharacterTile tests (#3996) — the Hall's start-a-character tile and its
 * full-slots state.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NewCharacterTile } from '../NewCharacterTile';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { CharacterSlots } from '@/evennia_replacements/types';
import type { MyRosterEntry } from '@/roster/types';

const mockFreeze = vi.fn();
const mockThaw = vi.fn();
const mockGiveUp = vi.fn();
vi.mock('@/roster/queries', () => ({
  useFreezeEntryMutation: () => ({ mutate: mockFreeze, isPending: false }),
  useThawEntryMutation: () => ({ mutate: mockThaw, isPending: false }),
  useGiveUpEntryMutation: () => ({ mutate: mockGiveUp, isPending: false }),
}));

function entry(id: number, name: string, provenance: string): MyRosterEntry {
  return {
    id,
    name,
    character_id: id + 40,
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
    activity_requirement: provenance === 'player' ? 'NONE' : 'HIGH',
    creation_provenance: provenance,
    thaw_available_at: null,
  };
}

const aria = entry(1, 'Aria', 'player');
const bram = entry(2, 'Bram', 'staff');

const roomy: CharacterSlots = {
  total: 4,
  used: 1,
  activity_total: 1,
  activity_used: 0,
  holders: [{ kind: 'character', name: 'Aria', roster_entry_id: 1, counts: true, activity: false }],
};

const full: CharacterSlots = {
  total: 2,
  used: 2,
  activity_total: 1,
  activity_used: 1,
  holders: [
    { kind: 'character', name: 'Aria', roster_entry_id: 1, counts: true, activity: false },
    { kind: 'character', name: 'Bram', roster_entry_id: 2, counts: true, activity: true },
  ],
};

describe('NewCharacterTile', () => {
  afterEach(() => vi.clearAllMocks());

  it('shows the count and both start actions with a free slot', () => {
    renderWithProviders(<NewCharacterTile slots={roomy} characters={[aria]} />);
    expect(screen.getByText('1 of 4')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Browse the roster' })).toHaveAttribute(
      'href',
      '/roster'
    );
    expect(screen.getByRole('link', { name: 'Create a character' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
  });

  it('shows no count for an exempt account', () => {
    renderWithProviders(<NewCharacterTile slots={{ ...roomy, total: null }} characters={[aria]} />);
    expect(screen.queryByText(/ of /)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Create a character' })).toBeInTheDocument();
  });

  it('disables the actions when full and names each holder with its free-up action', () => {
    renderWithProviders(<NewCharacterTile slots={full} characters={[aria, bram]} />);
    expect(screen.getByRole('button', { name: 'Browse the roster' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Create a character' })).toBeDisabled();
    const list = screen.getByRole('list', { name: 'Holding your slots' });
    expect(list).toHaveTextContent('Aria');
    expect(list).toHaveTextContent('Bram');
    expect(screen.getByRole('button', { name: 'Freeze' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Give up' })).toBeInTheDocument();
  });

  it('lists a draft with a link back into character creation', () => {
    const withDraft: CharacterSlots = {
      ...full,
      holders: [
        ...full.holders.slice(0, 1),
        { kind: 'draft', name: 'draft', roster_entry_id: null, counts: true, activity: false },
      ],
    };
    renderWithProviders(<NewCharacterTile slots={withDraft} characters={[aria]} />);
    expect(screen.getByRole('link', { name: 'Finish or discard' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
  });

  it('confirms a give-up and runs the mutation for that entry', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewCharacterTile slots={full} characters={[aria, bram]} />);
    await user.click(screen.getByRole('button', { name: 'Give up' }));
    expect(screen.getByText('Give up Bram?')).toBeInTheDocument();
    expect(screen.getByText(/returns to the roster for other players/)).toBeInTheDocument();
    await user.click(screen.getByTestId('slot-action-confirm'));
    expect(mockGiveUp).toHaveBeenCalledWith(2, expect.anything());
    expect(mockFreeze).not.toHaveBeenCalled();
  });
});
