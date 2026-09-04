import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { ReauthDialog } from '../components/ReauthDialog';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

const reauthenticateWithPassword = vi.fn();
const reauthenticateWithCode = vi.fn();

vi.mock('../api', () => ({
  reauthenticateWithPassword: (...args: unknown[]) => reauthenticateWithPassword(...args),
  reauthenticateWithCode: (...args: unknown[]) => reauthenticateWithCode(...args),
}));

describe('ReauthDialog', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('posts a password and calls onSuccess', async () => {
    reauthenticateWithPassword.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <ReauthDialog open flows={['reauthenticate']} onSuccess={onSuccess} onCancel={vi.fn()} />
    );

    await user.type(screen.getByLabelText('Password'), 'hunter2');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(reauthenticateWithPassword).toHaveBeenCalledWith('hunter2');
    expect(reauthenticateWithCode).not.toHaveBeenCalled();
  });

  it('shows the code prompt when flows are mfa_reauthenticate', async () => {
    reauthenticateWithCode.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <ReauthDialog open flows={['mfa_reauthenticate']} onSuccess={onSuccess} onCancel={vi.fn()} />
    );

    expect(screen.getByLabelText('Authenticator code')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Authenticator code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(reauthenticateWithCode).toHaveBeenCalledWith('123456');
    expect(reauthenticateWithPassword).not.toHaveBeenCalled();
  });
});
