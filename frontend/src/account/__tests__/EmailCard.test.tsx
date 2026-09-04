import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { EmailCard } from '../components/EmailCard';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

const useEmailAddresses = vi.fn();
const useRequestEmailChange = vi.fn();
const useResendEmailChange = vi.fn();
const useCancelEmailChange = vi.fn();
const useReauthGuard = vi.fn();

vi.mock('../hooks', () => ({
  useEmailAddresses: (...args: unknown[]) => useEmailAddresses(...args),
  useRequestEmailChange: (...args: unknown[]) => useRequestEmailChange(...args),
  useResendEmailChange: (...args: unknown[]) => useResendEmailChange(...args),
  useCancelEmailChange: (...args: unknown[]) => useCancelEmailChange(...args),
  useReauthGuard: (...args: unknown[]) => useReauthGuard(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';

function mockGuard() {
  useReauthGuard.mockReturnValue({
    run: (fn: () => Promise<unknown>) => fn(),
    dialogProps: { open: false, flows: [], onSuccess: vi.fn(), onCancel: vi.fn() },
  });
}

describe('EmailCard', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the current address with a Verified badge', () => {
    useEmailAddresses.mockReturnValue({
      data: [{ email: 'tester@test.com', verified: true, primary: true }],
      isLoading: false,
    });
    useRequestEmailChange.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    useResendEmailChange.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useCancelEmailChange.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();

    renderWithProviders(<EmailCard />);

    expect(screen.getByTestId('current-email')).toHaveTextContent('tester@test.com');
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('shows the pending block with Resend and Cancel for an unverified second address', () => {
    useEmailAddresses.mockReturnValue({
      data: [
        { email: 'tester@test.com', verified: true, primary: true },
        { email: 'new@test.com', verified: false, primary: false },
      ],
      isLoading: false,
    });
    useRequestEmailChange.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    useResendEmailChange.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useCancelEmailChange.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();

    renderWithProviders(<EmailCard />);

    const pending = screen.getByTestId('pending-email');
    expect(pending).toHaveTextContent('new@test.com');
    expect(screen.getByRole('button', { name: 'Resend' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel change' })).toBeInTheDocument();
  });

  it('submits the change and toasts', async () => {
    useEmailAddresses.mockReturnValue({
      data: [{ email: 'tester@test.com', verified: true, primary: true }],
      isLoading: false,
    });
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    useRequestEmailChange.mockReturnValue({ mutateAsync, isPending: false });
    useResendEmailChange.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useCancelEmailChange.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();

    const user = userEvent.setup();
    renderWithProviders(<EmailCard />);

    await user.type(screen.getByLabelText('Change email'), 'new@address.example');
    await user.click(screen.getByRole('button', { name: 'Send verification' }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith('new@address.example'));
    expect(toast.success).toHaveBeenCalledWith(
      'Check new@address.example for a verification link. Your current address stays active until then.'
    );
  });
});
