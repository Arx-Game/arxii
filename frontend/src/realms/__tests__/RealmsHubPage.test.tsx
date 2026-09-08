import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RealmsHubPage } from '../pages/RealmsHubPage';

vi.mock('../queries', () => ({
  useRealms: () => ({
    data: [
      {
        id: 1,
        name: 'Umbros',
        slug: 'umbros',
        formal_name: 'The Umbral Empire',
        theme: 'umbros',
        first_motto: 'Dare Greatly.',
      },
      { id: 2, name: 'Luxen', slug: 'luxen', formal_name: '', theme: 'luxen', first_motto: '' },
    ],
    isLoading: false,
  }),
}));

describe('RealmsHubPage (#3725)', () => {
  it('renders one card per realm, each a link to its page, in its own palette', () => {
    renderWithProviders(<RealmsHubPage />);
    const umbros = screen.getByRole('link', { name: /umbros/i });
    expect(umbros).toHaveAttribute('href', '/realms/umbros');
    expect(umbros).toHaveAttribute('data-realm', 'umbros');
    expect(screen.getByText('The Umbral Empire')).toBeInTheDocument();
    expect(screen.getByText('Dare Greatly.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /luxen/i })).toHaveAttribute('href', '/realms/luxen');
  });

  it('shows nothing beyond name, formal name and motto', () => {
    renderWithProviders(<RealmsHubPage />);
    const luxen = screen.getByRole('link', { name: /luxen/i });
    expect(luxen.textContent).toBe('Luxen');
  });
});
