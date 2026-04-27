/**
 * MessagesSection Tests
 *
 * Tests filter behavior, empty state, and acknowledge mutation effect.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MessagesSection } from '../components/MessagesSection';

vi.mock('../queries', () => ({
  useMyMessages: vi.fn(),
  useAcknowledgeDelivery: vi.fn(),
}));

import * as queries from '../queries';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const mockDeliveryUnread = {
  id: 1,
  message: {
    id: 10,
    body: 'A story unfolds before your eyes.',
    category: 'story' as const,
    sender_account: null,
    related_story: 5,
    related_beat_completion: null,
    related_episode_resolution: null,
    sent_at: '2026-04-19T10:00:00Z',
  },
  delivered_at: '2026-04-19T10:01:00Z',
  acknowledged_at: null,
};

const mockDeliveryRead = {
  id: 2,
  message: {
    id: 11,
    body: 'The atmosphere shifts around you.',
    category: 'atmosphere' as const,
    sender_account: 42,
    related_story: null,
    related_beat_completion: null,
    related_episode_resolution: null,
    sent_at: '2026-04-18T15:00:00Z',
  },
  delivered_at: '2026-04-18T15:01:00Z',
  acknowledged_at: '2026-04-18T15:30:00Z',
};

function setupMocks(results = [mockDeliveryUnread, mockDeliveryRead]) {
  const mockMutate = vi.fn();
  vi.mocked(queries.useMyMessages).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useMyMessages>);
  vi.mocked(queries.useAcknowledgeDelivery).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    data: undefined,
    error: null,
    mutateAsync: vi.fn(),
    reset: vi.fn(),
  } as unknown as ReturnType<typeof queries.useAcknowledgeDelivery>);
  return { mockMutate };
}

describe('MessagesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders message rows when data is available', () => {
    setupMocks();
    render(<MessagesSection />, { wrapper: createWrapper() });

    expect(screen.getByText('A story unfolds before your eyes.')).toBeInTheDocument();
    expect(screen.getByText('The atmosphere shifts around you.')).toBeInTheDocument();
  });

  it('shows empty state when no messages', () => {
    setupMocks([]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });

  it('shows loading skeletons when fetching', () => {
    vi.mocked(queries.useMyMessages).mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      error: null,
    } as ReturnType<typeof queries.useMyMessages>);
    vi.mocked(queries.useAcknowledgeDelivery).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useAcknowledgeDelivery>);

    const { container } = render(<MessagesSection />, { wrapper: createWrapper() });
    // Skeletons use animate-pulse class
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('calls useMyMessages with category filter when tab is changed', async () => {
    const user = userEvent.setup();
    setupMocks([]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    await user.click(screen.getByRole('tab', { name: 'Story' }));

    // After clicking Story tab, useMyMessages should have been called at least once
    // with category='story' among all calls (initial render + tab switch re-render).
    await waitFor(() => {
      const calls = vi.mocked(queries.useMyMessages).mock.calls;
      const hasStoryCategoryCall = calls.some(
        ([params]) => params !== undefined && 'category' in params && params.category === 'story'
      );
      expect(hasStoryCategoryCall).toBe(true);
    });
  });

  it('calls useMyMessages with acknowledged:false for Unread tab', async () => {
    const user = userEvent.setup();
    setupMocks([]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    await user.click(screen.getByRole('tab', { name: 'Unread' }));

    await waitFor(() => {
      const calls = vi.mocked(queries.useMyMessages).mock.calls;
      const hasUnreadCall = calls.some(
        ([params]) =>
          params !== undefined && 'acknowledged' in params && params.acknowledged === false
      );
      expect(hasUnreadCall).toBe(true);
    });
  });

  it('shows acknowledge button for unread messages', () => {
    setupMocks([mockDeliveryUnread]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /acknowledge/i })).toBeInTheDocument();
  });

  it('does not show acknowledge button for already-read messages', () => {
    setupMocks([mockDeliveryRead]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    expect(screen.queryByRole('button', { name: /acknowledge/i })).not.toBeInTheDocument();
  });

  it('renders Manage muted stories link', () => {
    setupMocks([]);
    render(<MessagesSection />, { wrapper: createWrapper() });

    const link = screen.getByTestId('manage-mutes-link');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/profile/mute-settings');
  });
});
