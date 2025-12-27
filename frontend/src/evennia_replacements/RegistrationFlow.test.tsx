/**
 * Integration test for the complete registration -> verification -> login flow.
 *
 * This test simulates the full user journey through the authentication system
 * to systematically verify that all components work together correctly.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import * as api from './api';
import { RegisterPage } from './RegisterPage';
import { EmailVerificationPendingPage } from './EmailVerificationPendingPage';
import { EmailVerifyPage } from './EmailVerifyPage';
import { LoginPage } from './LoginPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: vi.fn(),
  };
});

describe('Registration Flow Integration', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockNavigate.mockClear();
  });

  it('completes full registration -> verification -> login flow', async () => {
    // Step 1: User registers
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockResolvedValue({
      success: true,
      emailVerificationRequired: true,
    });

    const { unmount } = renderWithProviders(<RegisterPage />, {
      initialEntries: ['/register'],
    });

    // Fill out registration form
    await userEvent.type(screen.getByLabelText('Username'), 'newuser');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'newuser@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'SecurePass123!');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'SecurePass123!');
    await userEvent.tab();

    const registerButton = screen.getByRole('button', { name: /register/i });
    await userEvent.click(registerButton);

    // Verify registration API was called
    await waitFor(() => {
      expect(api.postRegister).toHaveBeenCalledWith({
        username: 'newuser',
        email: 'newuser@test.com',
        password: 'SecurePass123!',
      });
    });

    // Verify navigation to verification pending page
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/register/verify-email');
    });

    unmount();

    // Step 2: User sees "Check Your Email" page
    mockNavigate.mockClear();
    const { unmount: unmount2 } = renderWithProviders(<EmailVerificationPendingPage />, {
      initialEntries: ['/register/verify-email'],
    });

    expect(screen.getByText('Check Your Email')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeInTheDocument();

    unmount2();

    // Step 3: User clicks verification link in email
    mockNavigate.mockClear();
    const verificationKey = 'abc123def456';

    // Mock useParams to return the key
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: verificationKey });
    vi.mocked(api.verifyEmail).mockResolvedValue(undefined);

    const { unmount: unmount3 } = renderWithProviders(<EmailVerifyPage />, {
      initialEntries: [`/verify-email/${verificationKey}`],
    });

    // Should see verifying state
    expect(screen.getByText('Verifying Your Email')).toBeInTheDocument();

    // Wait for verification to complete
    await waitFor(() => {
      expect(api.verifyEmail).toHaveBeenCalledWith(verificationKey);
    });

    // Should see success message
    await waitFor(() => {
      expect(screen.getByText('Email Verified!')).toBeInTheDocument();
    });

    // Should auto-redirect to login
    await waitFor(
      () => {
        expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
      },
      { timeout: 3000 }
    );

    unmount3();

    // Step 4: User logs in with verified account
    mockNavigate.mockClear();
    vi.mocked(api.postLogin).mockResolvedValue({
      id: 1,
      username: 'newuser',
      email: 'newuser@test.com',
      is_staff: false,
    });

    renderWithProviders(<LoginPage />, {
      initialEntries: ['/login'],
    });

    await userEvent.type(screen.getByPlaceholderText('Username or Email'), 'newuser');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'SecurePass123!');
    await userEvent.click(screen.getByRole('button', { name: /log in/i }));

    // Verify login API was called
    await waitFor(() => {
      expect(api.postLogin).toHaveBeenCalledWith({
        login: 'newuser',
        password: 'SecurePass123!',
      });
    });

    // Should navigate to home after successful login
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });

  it('handles registration with email verification required', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockResolvedValue({
      success: true,
      emailVerificationRequired: true,
    });

    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'testuser');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@example.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'password123');
    await userEvent.tab();

    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/register/verify-email');
    });
  });

  it('handles registration without email verification (immediate login)', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockResolvedValue({
      success: true,
      emailVerificationRequired: false,
    });

    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'testuser');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@example.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'password123');
    await userEvent.tab();

    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    // Should navigate directly to home (user is logged in)
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });

  it('allows user to resend verification email', async () => {
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

  it('handles expired verification key gracefully', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'expired-key' });
    vi.mocked(api.verifyEmail).mockRejectedValue(new Error('Email confirmation key has expired'));

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    expect(screen.getByText('Email confirmation key has expired')).toBeInTheDocument();

    // Should provide way to resend
    const resendLink = screen.getByRole('link', { name: /resend verification email/i });
    expect(resendLink).toHaveAttribute('href', '/register/verify-email');
  });

  it('handles invalid verification key', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'invalid-key' });
    vi.mocked(api.verifyEmail).mockRejectedValue(new Error('Invalid email confirmation key'));

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    expect(screen.getByText('Invalid email confirmation key')).toBeInTheDocument();

    // Should provide links to recover
    expect(screen.getByRole('link', { name: /resend verification email/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to registration/i })).toBeInTheDocument();
  });
});
