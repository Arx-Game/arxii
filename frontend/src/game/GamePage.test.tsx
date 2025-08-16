import { screen } from '@testing-library/react';
import { GamePage } from './GamePage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';

describe('GamePage', () => {
  beforeEach(() => {
    store.dispatch(setAccount(null));
  });

  it('prompts to log in when not authenticated', () => {
    renderWithProviders(<GamePage />);
    expect(screen.getByText(/you must be logged in/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: /register/i })).toHaveAttribute('href', '/register');
  });

  it('shows game interface when authenticated', () => {
    store.dispatch(setAccount(mockAccount));
    renderWithProviders(<GamePage />);
    expect(screen.queryByText(/you must be logged in/i)).not.toBeInTheDocument();
  });
});
