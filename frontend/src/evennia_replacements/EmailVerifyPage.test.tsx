import { screen, waitFor } from '@testing-library/react';
import { EmailVerifyPage } from './EmailVerifyPage';
import { vi } from 'vitest';
import * as api from './api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

// Mock useParams to simulate URL parameter
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: vi.fn(),
    useNavigate: () => mockNavigate,
  };
});

describe('EmailVerifyPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockNavigate.mockClear();
  });

  it('shows verifying state initially', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'test-key-123' });

    // Make verifyEmail hang so we can see the loading state
    let resolveVerify: () => void = () => {};
    vi.mocked(api.verifyEmail).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveVerify = resolve;
        })
    );

    renderWithProviders(<EmailVerifyPage />);

    expect(screen.getByText('Verifying Your Email')).toBeInTheDocument();
    expect(
      screen.getByText('Please wait while we verify your email address...')
    ).toBeInTheDocument();

    // Clean up
    resolveVerify();
  });

  it('verifies email successfully and redirects', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'valid-key-456' });
    vi.mocked(api.verifyEmail).mockResolvedValue(undefined);

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(api.verifyEmail).toHaveBeenCalledWith('valid-key-456');
    });

    await waitFor(() => {
      expect(screen.getByText('Email Verified!')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Your email address has been successfully verified/)
    ).toBeInTheDocument();

    // Should auto-redirect after 2 seconds
    await waitFor(
      () => {
        expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
      },
      { timeout: 3000 }
    );
  });

  it('shows error when key is missing', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({});

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    expect(screen.getByText('Invalid verification link - missing key')).toBeInTheDocument();
    expect(api.verifyEmail).not.toHaveBeenCalled();
  });

  it('shows error when verification fails', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'invalid-key' });
    vi.mocked(api.verifyEmail).mockRejectedValue(new Error('Invalid email confirmation key'));

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    expect(screen.getByText('Invalid email confirmation key')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /resend verification email/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to registration/i })).toBeInTheDocument();
  });

  it('shows generic error message when error has no message', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'bad-key' });
    vi.mocked(api.verifyEmail).mockRejectedValue('Unknown error');

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Failed to verify email. The link may be expired or invalid./)
    ).toBeInTheDocument();
  });

  it('provides link to resend verification email on error', async () => {
    const { useParams } = await import('react-router-dom');
    vi.mocked(useParams).mockReturnValue({ key: 'expired-key' });
    vi.mocked(api.verifyEmail).mockRejectedValue(new Error('Email confirmation key has expired'));

    renderWithProviders(<EmailVerifyPage />);

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    const resendLink = screen.getByRole('link', { name: /resend verification email/i });
    expect(resendLink).toHaveAttribute('href', '/register/verify-email');
  });
});
