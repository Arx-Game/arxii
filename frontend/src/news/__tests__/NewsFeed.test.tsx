/**
 * NewsFeed (#1450) — the public-reaction feed renders deeds + scandals, shows an empty state when
 * nothing is circulating, and prompts for an active character when there is none. Mocks the query
 * hook so the feed sees its data synchronously.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { NewsFeed } from '../components/NewsFeed';
import type { PublicFeedItem } from '../types';

vi.mock('@/news/queries', () => ({
  usePublicFeedQuery: vi.fn(),
}));

import { usePublicFeedQuery } from '@/news/queries';

const mockQuery = vi.mocked(usePublicFeedQuery);

function mockFeed(data: PublicFeedItem[] | undefined): void {
  mockQuery.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof usePublicFeedQuery>);
}

describe('NewsFeed', () => {
  it('renders a deed and a scandal with their subjects', () => {
    mockFeed([
      {
        kind: 'deed',
        headline: 'slew the wyrm',
        subject: 'Ser Bran',
        occurred_at: '2026-06-24T00:00:00Z',
      },
      {
        kind: 'scandal',
        headline: 'consorts with the abyss',
        subject: 'Lady Vyper',
        occurred_at: '2026-06-24T00:00:00Z',
      },
    ]);
    render(<NewsFeed viewerId={1} />);

    expect(screen.getByText('slew the wyrm')).toBeInTheDocument();
    expect(screen.getByText('Ser Bran')).toBeInTheDocument();
    expect(screen.getByText('consorts with the abyss')).toBeInTheDocument();
    expect(screen.getByText('Scandal')).toBeInTheDocument();
  });

  it('shows an empty state when nothing is circulating', () => {
    mockFeed([]);
    render(<NewsFeed viewerId={1} />);

    expect(screen.getByText(/no news circulating/i)).toBeInTheDocument();
  });

  it('prompts for an active character when there is none', () => {
    mockFeed(undefined);
    render(<NewsFeed viewerId={null} />);

    expect(screen.getByText(/choose an active character/i)).toBeInTheDocument();
  });
});
