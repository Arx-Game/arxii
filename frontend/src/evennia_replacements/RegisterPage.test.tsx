import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RegisterPage } from './RegisterPage';
import { vi } from 'vitest';
import * as api from './api';
import { mockAccount } from '@/test/mocks/account';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { AccountData } from './types';

vi.mock('./api');

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    store.dispatch(setAccount(null));
  });

  it('registers and stores account data', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    vi.mocked(api.postRegister).mockResolvedValue(mockAccount);
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(api.postRegister).toHaveBeenCalledWith({
        username: 'tester',
        email: 'test@test.com',
        password: 'secret',
      });
      expect(store.getState().auth.account).toEqual(mockAccount);
    });
  });

  it('shows error when username already taken', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(false);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
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

    await userEvent.type(screen.getByPlaceholderText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.tab();
    await userEvent.click(screen.getByRole('button', { name: /register/i }));

    await waitFor(() => {
      expect(screen.getByText(/email already taken/i)).toBeInTheDocument();
      expect(api.postRegister).not.toHaveBeenCalled();
    });
  });

  it('disables submit while registering', async () => {
    vi.mocked(api.checkUsername).mockResolvedValue(true);
    vi.mocked(api.checkEmail).mockResolvedValue(true);
    let resolve: (value: AccountData) => void = () => {};
    vi.mocked(api.postRegister).mockImplementation(
      () =>
        new Promise((res) => {
          resolve = res;
        })
    );
    renderWithProviders(<RegisterPage />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'tester');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Email'), 'test@test.com');
    await userEvent.tab();
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret');
    await userEvent.tab();
    const button = screen.getByRole('button', { name: /register/i });
    await userEvent.click(button);

    expect(button).toBeDisabled();

    await act(async () => {
      resolve(mockAccount);
    });
  });
});
