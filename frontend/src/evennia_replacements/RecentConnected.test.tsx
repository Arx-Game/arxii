import { screen } from '@testing-library/react';
import { RecentConnected } from './RecentConnected';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

describe('RecentConnected', () => {
  it('renders loading state', () => {
    renderWithProviders(<RecentConnected isLoading={true} />);

    expect(screen.getByText('Recently Connected')).toBeInTheDocument();
    // Should show skeleton loaders (check for elements with animate-pulse class)
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons).toHaveLength(6); // 3 avatars + 3 name skeletons
  });

  it('renders entries with valid data', () => {
    const entries = [
      { id: 1, name: 'Alice', avatar_url: 'https://example.com/alice.jpg' },
      { id: 2, name: 'Bob', avatar_url: 'https://example.com/bob.jpg' },
    ];

    renderWithProviders(<RecentConnected entries={entries} isLoading={false} />);

    expect(screen.getByText('Recently Connected')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('AL')).toBeInTheDocument(); // Avatar fallback
    expect(screen.getByText('BO')).toBeInTheDocument(); // Avatar fallback
  });

  it('handles entries with undefined names gracefully', () => {
    const entries = [
      {
        id: 1,
        name: undefined as unknown as string,
        avatar_url: 'https://example.com/unknown.jpg',
      },
      { id: 2, name: '', avatar_url: 'https://example.com/empty.jpg' },
    ];

    renderWithProviders(<RecentConnected entries={entries} isLoading={false} />);

    expect(screen.getByText('Recently Connected')).toBeInTheDocument();
    // Should show fallback avatars without crashing - both entries will show "??"
    const fallbackAvatars = screen.getAllByText('??');
    expect(fallbackAvatars).toHaveLength(2);
  });

  it('handles empty entries array', () => {
    renderWithProviders(<RecentConnected entries={[]} isLoading={false} />);

    expect(screen.getByText('Recently Connected')).toBeInTheDocument();
    // Should not crash with empty array
  });

  it('handles undefined entries prop', () => {
    renderWithProviders(<RecentConnected isLoading={false} />);

    expect(screen.getByText('Recently Connected')).toBeInTheDocument();
    // Should not crash with undefined entries
  });
});
