/**
 * WorldBand tests (#3412 slice 2) — the Hall's "The World" band: calendar,
 * Occasions, The Crier all render from mocked queries; the persona tidings
 * digest plate is docked-only.
 */
import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { WorldBand } from '../WorldBand';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { hydrateActiveCharacter, resetGame } from '@/store/gameSlice';
import type { EventListItem } from '@/events/types';
import type { Gemit } from '@/narrative/types';

const mockUseClockQuery = vi.fn();
vi.mock('../queries', () => ({
  useClockQuery: () => mockUseClockQuery(),
}));

const mockFetchEvents = vi.fn();
vi.mock('@/events/queries', () => ({
  fetchEvents: (params: Record<string, string>) => mockFetchEvents(params),
}));

const mockUseGemits = vi.fn();
vi.mock('@/narrative/queries', () => ({
  useGemits: (...args: unknown[]) => mockUseGemits(...args),
}));

const mockTidingsFeed = vi.fn();
vi.mock('@/tidings/components/TidingsFeed', () => ({
  TidingsFeed: (props: { viewerId: number }) => {
    mockTidingsFeed(props);
    return <div data-testid="tidings-feed-stub" />;
  },
}));

const upcomingEvent: EventListItem = {
  id: 1,
  name: "The Lamplighter's Ball",
  description: '',
  location: 1,
  location_name: 'the Ward of the Compact',
  status: 'scheduled',
  is_public: true,
  scheduled_real_time: '2026-09-01T20:00:00Z',
  scheduled_ic_time: null,
  time_phase: 'night',
  primary_host_name: 'Aria',
};

const gemit: Gemit = {
  id: 1,
  body: 'A tower falls in the Ward.',
  sender_account: null,
  related_era: null,
  related_story: null,
  sent_at: '2026-08-20T12:00:00Z',
};

function setDefaultMocks() {
  mockUseClockQuery.mockReturnValue({
    data: {
      ic_datetime: '2026-08-20T12:00:00Z',
      year: 1247,
      month: 3,
      day: 12,
      hour: 14,
      minute: 5,
      phase: 'day',
      season: 'summer',
      light_level: 1,
      paused: false,
    },
  });
  mockFetchEvents.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  mockUseGemits.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] } });
}

describe('WorldBand', () => {
  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('renders the calendar plate fields plainly (no invented calendar lore)', () => {
    setDefaultMocks();
    renderWithProviders(<WorldBand />);

    expect(screen.getByText(/Year 1247, Month 3, Day 12/)).toBeInTheDocument();
    expect(screen.getByText(/Summer, Day/)).toBeInTheDocument();
  });

  it('requests upcoming events for the Occasions plate and renders them', async () => {
    setDefaultMocks();
    mockFetchEvents.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [upcomingEvent],
    });
    renderWithProviders(<WorldBand />);

    expect(mockFetchEvents).toHaveBeenCalledWith({ upcoming: 'true' });
    expect(await screen.findByText("The Lamplighter's Ball")).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All occasions →' })).toHaveAttribute(
      'href',
      '/events'
    );
  });

  it('renders the first page of gemits in The Crier plate', () => {
    setDefaultMocks();
    mockUseGemits.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [gemit] },
    });
    renderWithProviders(<WorldBand />);

    expect(screen.getByText('A tower falls in the Ward.')).toBeInTheDocument();
  });

  it('the Crier plate ends with the last gemit — no "full record" affordance (review fix, no archive page exists)', () => {
    setDefaultMocks();
    mockUseGemits.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [gemit] },
    });
    renderWithProviders(<WorldBand />);

    expect(screen.queryByText(/full record/i)).not.toBeInTheDocument();
  });

  it('omits the persona tidings digest plate when no character is docked', () => {
    setDefaultMocks();
    renderWithProviders(<WorldBand />);

    expect(screen.queryByTestId('tidings-feed-stub')).not.toBeInTheDocument();
  });

  it('renders the persona tidings digest plate ONLY when a character is docked', async () => {
    setDefaultMocks();
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));
    renderWithProviders(<WorldBand />);

    await waitFor(() => {
      expect(screen.getByTestId('tidings-feed-stub')).toBeInTheDocument();
    });
    expect(mockTidingsFeed).toHaveBeenCalledWith(expect.objectContaining({ viewerId: 1 }));
  });
});
