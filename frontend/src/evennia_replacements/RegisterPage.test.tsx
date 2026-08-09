import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RegisterPage } from './RegisterPage';
import { vi } from 'vitest';
import * as api from './api';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('./api');

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    store.dispatch(setAccount(null));
  });

  it('registers and stores account data', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockResolvedValue({
      success: true,
      emailVerificationRequired: false,
    });
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(api.postRegister).toHaveBeenCalledWith({
        username: 'tester',
        email: 'test@test.com',
        password: 'secret',
      });
    });
  });

  it('shows error when username already taken', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(false);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(screen.getByText(/username already taken/i)).toBeInTheDocument();
      expect(api.postRegister).not.toHaveBeenCalled();
    });
  });

  it('shows error when email already taken', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(false);
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(screen.getByText(/email already taken/i)).toBeInTheDocument();
      expect(api.postRegister).not.toHaveBeenCalled();
    });
  });

  it('shows the real server error message on a failed registration', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockRejectedValue(
      new Error('This password is too short. It must contain at least 8 characters.')
    );
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'short');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'short');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(screen.getByText(/this password is too short/i)).toBeInTheDocument();
    });
  });

  it('disables submit while registering', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    let resolve: (value: { success: true; emailVerificationRequired: boolean }) => void = () => {};
    vi.mocked(api.postRegister).mockImplementation(
      () =>
        new Promise((res) => {
          resolve = res;
        })
    );
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'secret');
    await userEvent.tab();
    const button = screen.getByRole('button', { name: /register/i });
    await userEvent.click(button);

    expect(button).toBeDisabled();

    await act(async () => {
      resolve({ success: true, emailVerificationRequired: false });
    });
  });

  it('auto-fills the invite code from the ?invite= query param', async () => {
    vi.mocked(api.fetchRegistrationStatus).mockResolvedValue({ open: false });
    renderWithProviders(<RegisterPage />, { initialEntries: ['/register?invite=abc123'] });

    expect(await screen.findByLabelText('Invite Code')).toHaveValue('abc123');
  });

  it('shows the invite-only notice when registration is closed and no invite is present', async () => {
    vi.mocked(api.fetchRegistrationStatus).mockResolvedValue({ open: false });
    renderWithProviders(<RegisterPage />);

    expect(await screen.findByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument();
  });

  it('shows the signup form when registration is closed but an invite link is present', async () => {
    vi.mocked(api.fetchRegistrationStatus).mockResolvedValue({ open: false });
    renderWithProviders(<RegisterPage />, { initialEntries: ['/register?invite=abc123'] });

    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(screen.queryByText(/invite-only/i)).not.toBeInTheDocument();
  });

  it('shows the signup form when registration is open', async () => {
    vi.mocked(api.fetchRegistrationStatus).mockResolvedValue({ open: true });
    renderWithProviders(<RegisterPage />);

    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
  });

  it('sends the invite token to postRegister when the invite field is filled', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.fetchRegistrationStatus).mockResolvedValue({ open: false });
    vi.mocked(api.postRegister).mockResolvedValue({
      success: true,
      emailVerificationRequired: false,
    });
    renderWithProviders(<RegisterPage />, { initialEntries: ['/register?invite=abc123'] });

    await screen.findByLabelText('Username');
    await userEvent.type(screen.getByLabelText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText('Confirm Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(api.postRegister).toHaveBeenCalledWith({
        username: 'tester',
        email: 'test@test.com',
        password: 'secret',
        inviteToken: 'abc123',
      });
    });
  });
});
