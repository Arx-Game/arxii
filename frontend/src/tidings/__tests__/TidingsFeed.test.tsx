/**
 * TidingsFeed (#1450) — the public-reaction feed renders deeds + scandals, shows an empty state
 * when nothing is circulating, and prompts for an active character when there is none. Mocks the
 * query hook so the feed sees its data synchronously.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TidingsFeed } from '../components/TidingsFeed';
import type { PublicFeedItem } from '../types';

vi.mock('@/tidings/queries', () => ({
  usePublicFeedQuery: vi.fn(),
}));

import { usePublicFeedQuery } from '@/tidings/queries';

const mockQuery = vi.mocked(usePublicFeedQuery);

function mockFeed(data: PublicFeedItem[] | undefined): void {
  mockQuery.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof usePublicFeedQuery>);
}

describe('TidingsFeed', () => {
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
    render(<TidingsFeed viewerId={1} />);

    expect(screen.getByText('slew the wyrm')).toBeInTheDocument();
    expect(screen.getByText('Ser Bran')).toBeInTheDocument();
    expect(screen.getByText('consorts with the abyss')).toBeInTheDocument();
    expect(screen.getByText('Scandal')).toBeInTheDocument();
  });

  it('shows an empty state when nothing is circulating', () => {
    mockFeed([]);
    render(<TidingsFeed viewerId={1} />);

    expect(screen.getByText(/no tidings circulating/i)).toBeInTheDocument();
  });

  it('prompts for an active character when there is none', () => {
    mockFeed(undefined);
    render(<TidingsFeed viewerId={null} />);

    expect(screen.getByText(/choose an active character/i)).toBeInTheDocument();
  });

  // #3412 review fix: the resolving window (account/roster hydration still in
  // flight) must show a skeleton, never the "choose a character" empty-state —
  // that message is only correct once resolution genuinely lands on no selection.
  it('shows a loading skeleton, not the empty-state, while the viewer is still resolving', () => {
    mockFeed(undefined);
    render(<TidingsFeed viewerId={null} isResolvingViewer />);

    expect(screen.queryByText(/choose an active character/i)).not.toBeInTheDocument();
  });

  it('renders a distinct label for every PublicFeedItemKindEnum value', () => {
    const kinds = [
      'deed',
      'scandal',
      'pardon',
      'crisis',
      'proclamation',
      'birthday',
      'stature',
      'menace',
      'verdict',
    ] as const;
    mockFeed(
      kinds.map((kind, index) => ({
        kind,
        headline: `headline-${index}`,
        subject: `subject-${index}`,
        occurred_at: '2026-06-24T00:00:00Z',
      }))
    );
    render(<TidingsFeed viewerId={1} />);

    const labels = [
      'Deed',
      'Scandal',
      'Pardon',
      'Crisis',
      'Proclamation',
      'Birthday',
      'Stature',
      'Menace',
      'Verdict',
    ];
    const seen = new Set(labels.map((label) => screen.getByText(label).textContent));
    expect(seen.size).toBe(labels.length);
  });
});
