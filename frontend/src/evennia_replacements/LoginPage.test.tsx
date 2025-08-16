import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from './LoginPage';
import { vi } from 'vitest';
import * as api from './api';
import { mockAccount } from '@/test/mocks/account';
import { store } from '@/store/store';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

describe('LoginPage', () => {
  it('logs in and stores account data', async () => {
    vi.mocked(api.postLogin).mockResolvedValue(mockAccount);
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));

    await waitFor(() => {
      expect(api.postLogin).toHaveBeenCalledWith({
        username: 'tester',
        password: 'secret',
      });
      expect(store.getState().auth.account).toEqual(mockAccount);
    });
  });

  it('has a link to register', () => {
    renderWithProviders(<LoginPage />);
    const link = screen.getByRole('link', { name: /register/i });
    expect(link).toHaveAttribute('href', '/register');
  });
});
