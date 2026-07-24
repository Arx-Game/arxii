import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { FeaturedLore } from '../FeaturedLore';

vi.mock('@/codex/queries', () => ({
  useFeaturedCodexEntries: vi.fn(),
}));

import { useFeaturedCodexEntries } from '@/codex/queries';

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

describe('FeaturedLore', () => {
  it('renders featured entries when loaded', () => {
    vi.mocked(useFeaturedCodexEntries).mockReturnValue({
      data: [
        {
          id: 1,
          name: 'The Gifted',
          summary: 'Those who carry magic',
          is_public: true,
          is_featured: true,
          featured_order: 1,
          subject: 1,
          subject_name: 'The World',
          subject_path: [],
          display_order: 1,
          knowledge_status: null,
          art_url: null,
        },
      ],
      isLoading: false,
      isError: false,
    } as never);

    render(<FeaturedLore />, { wrapper: createWrapper() });

    expect(screen.getByText('The Gifted')).toBeInTheDocument();
  });

  it('renders empty state link when no entries', () => {
    vi.mocked(useFeaturedCodexEntries).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as never);

    render(<FeaturedLore />, { wrapper: createWrapper() });

    expect(screen.getByText(/Explore the world/i)).toBeInTheDocument();
  });
});
