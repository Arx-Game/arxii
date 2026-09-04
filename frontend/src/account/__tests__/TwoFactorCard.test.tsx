import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { TwoFactorCard } from '../components/TwoFactorCard';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';

const useAuthenticators = vi.fn();
const useSecuritySettings = vi.fn();
const useSetBlockTelnet = vi.fn();
const useDeactivateTotp = vi.fn();
const useReauthGuard = vi.fn();
const useActivateTotp = vi.fn();
const useRecoveryCodes = vi.fn();
const useRegenerateRecoveryCodes = vi.fn();

vi.mock('../hooks', () => ({
  useAuthenticators: (...args: unknown[]) => useAuthenticators(...args),
  useSecuritySettings: (...args: unknown[]) => useSecuritySettings(...args),
  useSetBlockTelnet: (...args: unknown[]) => useSetBlockTelnet(...args),
  useDeactivateTotp: (...args: unknown[]) => useDeactivateTotp(...args),
  useReauthGuard: (...args: unknown[]) => useReauthGuard(...args),
  useActivateTotp: (...args: unknown[]) => useActivateTotp(...args),
  useRecoveryCodes: (...args: unknown[]) => useRecoveryCodes(...args),
  useRegenerateRecoveryCodes: (...args: unknown[]) => useRegenerateRecoveryCodes(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function mockGuard() {
  useReauthGuard.mockReturnValue({
    run: (fn: () => Promise<unknown>) => fn(),
    dialogProps: { open: false, flows: [], onSuccess: vi.fn(), onCancel: vi.fn() },
  });
}

function mockChildDialogHooks() {
  useActivateTotp.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  useRecoveryCodes.mockReturnValue({ data: undefined, isLoading: false });
  useRegenerateRecoveryCodes.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
}

describe('TwoFactorCard', () => {
  afterEach(() => {
    vi.clearAllMocks();
    store.dispatch(setAccount(null));
  });

  it('shows Set up when 2FA is off', () => {
    store.dispatch(setAccount(mockAccount));
    useAuthenticators.mockReturnValue({ data: [], isLoading: false });
    useSecuritySettings.mockReturnValue({ data: { block_telnet_login_with_2fa: false } });
    useSetBlockTelnet.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useDeactivateTotp.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();
    mockChildDialogHooks();

    renderWithProviders(<TwoFactorCard />);

    expect(screen.getByRole('button', { name: 'Set up' })).toBeInTheDocument();
    expect(
      screen.queryByLabelText('Refuse telnet sign-in while 2FA is on')
    ).not.toBeInTheDocument();
  });

  it('shows the telnet switch only when 2FA is on and toggles it', async () => {
    store.dispatch(setAccount(mockAccount));
    useAuthenticators.mockReturnValue({
      data: [{ type: 'totp', created_at: 0, last_used_at: null }],
      isLoading: false,
    });
    useSecuritySettings.mockReturnValue({ data: { block_telnet_login_with_2fa: false } });
    const mutate = vi.fn();
    useSetBlockTelnet.mockReturnValue({ mutate, isPending: false });
    useDeactivateTotp.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();
    mockChildDialogHooks();

    const user = userEvent.setup();
    renderWithProviders(<TwoFactorCard />);

    expect(screen.queryByRole('button', { name: 'Set up' })).not.toBeInTheDocument();
    const toggle = screen.getByLabelText('Refuse telnet sign-in while 2FA is on');
    expect(toggle).toBeInTheDocument();

    await user.click(toggle);
    expect(mutate).toHaveBeenCalledWith(true, expect.anything());
  });

  it('hides Set up when the email is not verified', () => {
    store.dispatch(setAccount({ ...mockAccount, email_verified: false }));
    useAuthenticators.mockReturnValue({ data: [], isLoading: false });
    useSecuritySettings.mockReturnValue({ data: { block_telnet_login_with_2fa: false } });
    useSetBlockTelnet.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useDeactivateTotp.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockGuard();
    mockChildDialogHooks();

    renderWithProviders(<TwoFactorCard />);

    expect(screen.queryByRole('button', { name: 'Set up' })).not.toBeInTheDocument();
  });
});
