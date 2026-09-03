import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { PasswordCard } from '../components/PasswordCard';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

const useChangePassword = vi.fn();

vi.mock('../hooks', () => ({
  useChangePassword: (...args: unknown[]) => useChangePassword(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';

describe('PasswordCard', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('blocks mismatched confirms without calling the mutation', async () => {
    const mutateAsync = vi.fn();
    useChangePassword.mockReturnValue({ mutateAsync, isPending: false });

    const user = userEvent.setup();
    renderWithProviders(<PasswordCard />);

    await user.type(screen.getByLabelText('Current password'), 'oldpass');
    await user.type(screen.getByLabelText('New password'), 'newpass1');
    await user.type(screen.getByLabelText('New password again'), 'newpass2');
    await user.click(screen.getByRole('button', { name: 'Change password' }));

    expect(screen.getByText('The two new passwords do not match.')).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('submits current_password and new_password and toasts', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    useChangePassword.mockReturnValue({ mutateAsync, isPending: false });

    const user = userEvent.setup();
    renderWithProviders(<PasswordCard />);

    await user.type(screen.getByLabelText('Current password'), 'oldpass');
    await user.type(screen.getByLabelText('New password'), 'newpass1');
    await user.type(screen.getByLabelText('New password again'), 'newpass1');
    await user.click(screen.getByRole('button', { name: 'Change password' }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        current_password: 'oldpass',
        new_password: 'newpass1',
      })
    );
    expect(toast.success).toHaveBeenCalledWith('Password changed. You stay signed in.');
  });
});
