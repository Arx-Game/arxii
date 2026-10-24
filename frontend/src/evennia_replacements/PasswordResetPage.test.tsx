import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PasswordResetPage, PasswordResetRequestPage } from './PasswordResetPage';
import * as api from './api';

vi.mock('./api');

function renderReset() {
  return renderWithProviders(
    <Routes>
      <Route path="/reset-password/:key" element={<PasswordResetPage />} />
      <Route path="/reset-password" element={<PasswordResetRequestPage />} />
      <Route path="/login" element={<h1>Login</h1>} />
    </Routes>,
    { initialEntries: ['/reset-password/test-key'] }
  );
}

describe('Password recovery', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.validatePasswordResetKey).mockResolvedValue(undefined);
  });

  it('requests a link and gives a neutral inbox confirmation', async () => {
    vi.mocked(api.requestPasswordReset).mockResolvedValue(undefined);
    renderWithProviders(<PasswordResetRequestPage />);
    await userEvent.type(screen.getByLabelText('Email'), 'owner@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByRole('status')).toHaveTextContent('If an account uses that address');
    expect(api.requestPasswordReset).toHaveBeenCalledWith('owner@example.com');
    expect(screen.getByRole('link', { name: 'Back to login' })).toHaveAttribute('href', '/login');
  });

  it('prevents duplicate requests while sending and lets a failed request retry', async () => {
    let rejectRequest!: (reason: Error) => void;
    vi.mocked(api.requestPasswordReset).mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectRequest = reject;
        })
    );
    renderWithProviders(<PasswordResetRequestPage />);
    await userEvent.type(screen.getByLabelText('Email'), 'owner@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeDisabled();
    rejectRequest(new Error('Too many attempts. Please wait.'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many attempts');
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeEnabled();
  });

  it('explains an invalid link and offers a fresh request', async () => {
    vi.mocked(api.validatePasswordResetKey).mockRejectedValue(new Error('This link has expired.'));
    renderReset();
    expect(await screen.findByRole('alert')).toHaveTextContent('This link has expired.');
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Request a new reset link' }));
    expect(await screen.findByRole('heading', { name: 'Reset your password' })).toBeInTheDocument();
  });

  it('resets from a valid email link, handles validation, and leaves a stable login action', async () => {
    vi.mocked(api.confirmPasswordReset)
      .mockRejectedValueOnce(new Error('This password is too common.'))
      .mockResolvedValueOnce(undefined);
    renderReset();
    const password = await screen.findByLabelText('New password');
    const confirmation = screen.getByLabelText('Confirm new password');
    await userEvent.type(password, 'example-password');
    await userEvent.type(confirmation, 'different-password');
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Passwords must match.');
    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
    await userEvent.clear(confirmation);
    await userEvent.type(confirmation, 'example-password');
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This password is too common.');
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Your password has been changed.');
    expect(api.confirmPasswordReset).toHaveBeenLastCalledWith({
      key: 'test-key',
      password: 'example-password',
    });
    await userEvent.click(screen.getByRole('link', { name: 'Continue to login' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Login' })).toBeInTheDocument());
  });
});
