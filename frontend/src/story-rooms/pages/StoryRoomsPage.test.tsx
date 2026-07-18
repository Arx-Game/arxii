/**
 * StoryRoomsPage tests (#2450 Fix 2) — smoke tests mirroring
 * `stories/__tests__/GMDashboardPage.test.tsx`: renders the grants list and
 * the empty state.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';

import { StoryRoomsPage } from './StoryRoomsPage';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';

function withProviders(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StoryRoomsPage', () => {
  it('renders the empty state when there are no grants', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ count: 0, next: null, previous: null, page_size: 50, results: [] }),
    } as Response);

    render(withProviders(<StoryRoomsPage />));

    await waitFor(() => {
      expect(screen.getByText('No story invitations right now.')).toBeInTheDocument();
    });
  });

  it('renders a grant row with a Join button when not inside', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          count: 1,
          next: null,
          previous: null,
          page_size: 50,
          results: [
            {
              id: 1,
              room_id: 10,
              room_name: 'The Dungeon',
              character_id: 7,
              character_name: 'Grantee',
              is_inside: false,
              created_at: '2026-07-08T00:00:00Z',
            },
          ],
        }),
    } as Response);

    render(withProviders(<StoryRoomsPage />));

    await waitFor(() => {
      expect(screen.getByText('The Dungeon')).toBeInTheDocument();
    });
    expect(screen.getByText(/Granted to Grantee/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Join' })).toBeInTheDocument();
  });

  it('renders a Leave button when the character is already inside', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          count: 1,
          next: null,
          previous: null,
          page_size: 50,
          results: [
            {
              id: 1,
              room_id: 10,
              room_name: 'The Dungeon',
              character_id: 7,
              character_name: 'Grantee',
              is_inside: true,
              created_at: '2026-07-08T00:00:00Z',
            },
          ],
        }),
    } as Response);

    render(withProviders(<StoryRoomsPage />));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Leave' })).toBeInTheDocument();
    });
  });
});
