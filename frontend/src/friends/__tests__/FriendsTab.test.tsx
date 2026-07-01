/** FriendsTab (#1727) — lists the player's OOC friends and removes them. Mocks the hooks. */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FriendsTab } from '../components/FriendsTab';
import type { Friendship } from '../types';

const removeMutate = vi.fn();

vi.mock('@/friends/queries', () => ({
  useFriendsQuery: vi.fn(),
  useRemoveFriendMutation: vi.fn(() => ({ mutate: removeMutate, isPending: false })),
}));

import { useFriendsQuery } from '@/friends/queries';

const mockQuery = vi.mocked(useFriendsQuery);

function mockFriends(results: Friendship[]): void {
  mockQuery.mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useFriendsQuery>);
}

function friend(overrides: Partial<Friendship>): Friendship {
  return {
    id: 1,
    friender_tenure: 10,
    friend_tenure: 20,
    friend_name: 'Bob',
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  } as Friendship;
}

describe('FriendsTab', () => {
  it('lists friends by name', () => {
    mockFriends([friend({ friend_name: 'Bob' })]);
    render(<FriendsTab />);
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('empty state prompts to friend from another sheet', () => {
    mockFriends([]);
    render(<FriendsTab />);
    expect(screen.getByText(/no friends listed/i)).toBeInTheDocument();
  });

  it('removes a friend on click', () => {
    mockFriends([friend({ id: 7, friend_name: 'Bob' })]);
    render(<FriendsTab />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(removeMutate).toHaveBeenCalledWith(7);
  });
});
