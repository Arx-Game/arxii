import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { vi } from 'vitest';
import * as api from './api';
import { mockAccount } from '@/test/mocks/account';
import { store } from '@/store/store';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

describe('LoginPage', () => {
  it('logs in and stores account data', async () => {
    vi.mocked(api.postLogin).mockResolvedValue({ kind: 'ok', account: mockAccount });
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));

    await waitFor(() => {
      expect(api.postLogin).toHaveBeenCalledWith({
        login: 'tester',
        password: 'secret',
      });
      expect(store.getState().auth.account).toEqual(mockAccount);
    });
  });

  it('shows error when unverified user tries to login', async () => {
    // allauth headless returns an error for unverified users
    vi.mocked(api.postLogin).mockRejectedValue(new Error('Email verification required'));

    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'unverified');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText('Login failed. Please try again.')).toBeInTheDocument();
    });
  });

  it('has a link to register', () => {
    renderWithProviders(<LoginPage />);
    const link = screen.getByRole('link', { name: /register/i });
    expect(link).toHaveAttribute('href', '/register');
  });

  it('asks for a code when login needs a second factor, then completes', async () => {
    vi.mocked(api.postLogin).mockResolvedValue({ kind: 'mfa_required' });
    vi.mocked(api.completeMfaLogin).mockResolvedValue(mockAccount);
    renderWithProviders(<LoginPage />);
    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));
    const code = await screen.findByLabelText(/authenticator code or recovery code/i);
    await userEvent.type(code, '123456');
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await waitFor(() => {
      expect(api.completeMfaLogin).toHaveBeenCalledWith('123456');
      expect(store.getState().auth.account).toEqual(mockAccount);
    });
  });

  it('returns to a same-origin next path after login', async () => {
    vi.mocked(api.postLogin).mockResolvedValue({ kind: 'ok', account: mockAccount });
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/admin/" element={<div>admin home</div>} />
      </Routes>,
      { initialEntries: ['/login?next=/admin/'] }
    );
    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));
    expect(await screen.findByText('admin home')).toBeInTheDocument();
  });

  it('ignores an off-site next', async () => {
    vi.mocked(api.postLogin).mockResolvedValue({ kind: 'ok', account: mockAccount });
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>home</div>} />
      </Routes>,
      { initialEntries: ['/login?next=https://evil.example'] }
    );
    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));
    expect(await screen.findByText('home')).toBeInTheDocument();
  });
});
