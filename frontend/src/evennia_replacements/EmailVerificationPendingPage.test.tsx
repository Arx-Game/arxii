import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmailVerificationPendingPage } from './EmailVerificationPendingPage';
import { vi } from 'vitest';
import * as api from './api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

describe('EmailVerificationPendingPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows email verification instructions', () => {
    renderWithProviders(<EmailVerificationPendingPage />);

    expect(screen.getByText('Check Your Email')).toBeInTheDocument();
    expect(
      screen.getByText(
        /We've sent a verification email to your address. Please click the link in the email/
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/What's next?/)).toBeInTheDocument();
    expect(screen.getByText(/Check your email inbox/)).toBeInTheDocument();
    expect(screen.getByText(/Look in spam\/junk folders if needed/)).toBeInTheDocument();
    expect(screen.getByText(/Click the verification link/)).toBeInTheDocument();
    expect(screen.getByText(/Return here to log in/)).toBeInTheDocument();
  });

  it('has a resend verification button', () => {
    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });
    expect(resendButton).toBeInTheDocument();
    expect(resendButton).not.toBeDisabled();
  });

  it('resends verification email successfully', async () => {
    vi.mocked(api.resendEmailVerification).mockResolvedValue(undefined);
    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });

    await userEvent.click(resendButton);

    await waitFor(() => {
      expect(api.resendEmailVerification).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText('✓ Verification email resent successfully!')).toBeInTheDocument();
    });
  });

  it('shows loading state while resending', async () => {
    let resolveResend: () => void = () => {};
    vi.mocked(api.resendEmailVerification).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveResend = resolve;
        })
    );

    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });

    await userEvent.click(resendButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sending\.\.\./i })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /sending\.\.\./i })).toBeDisabled();

    // Clean up
    resolveResend();
  });

  it('shows error when resend fails', async () => {
    vi.mocked(api.resendEmailVerification).mockRejectedValue(new Error('Failed to resend email'));

    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });

    await userEvent.click(resendButton);

    await waitFor(() => {
      expect(screen.getByText('Failed to resend email')).toBeInTheDocument();
    });
  });

  it('shows generic error message when error has no message', async () => {
    vi.mocked(api.resendEmailVerification).mockRejectedValue('Unknown error');

    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });

    await userEvent.click(resendButton);

    await waitFor(() => {
      expect(screen.getByText('Failed to resend email')).toBeInTheDocument();
    });
  });

  it('re-enables button after error', async () => {
    vi.mocked(api.resendEmailVerification).mockRejectedValue(new Error('Server error'));

    renderWithProviders(<EmailVerificationPendingPage />);

    const resendButton = screen.getByRole('button', {
      name: /resend verification email/i,
    });

    await userEvent.click(resendButton);

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });

    expect(resendButton).not.toBeDisabled();
  });

  it('provides link to login page', () => {
    renderWithProviders(<EmailVerificationPendingPage />);

    const loginLink = screen.getByRole('link', { name: /already verified\? sign in/i });
    expect(loginLink).toHaveAttribute('href', '/login');
  });
});
