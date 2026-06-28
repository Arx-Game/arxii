/**
 * SettingsPage — Visibility (quiet/hidden mode) toggle tests (#1484).
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { SettingsPage } from '../SettingsPage';

vi.mock('@/roster/visibility', () => ({
  useVisibilitySettings: vi.fn(),
  useSetAppearOffline: vi.fn(),
}));

// Theme provider + connected-accounts pull from contexts/network we don't exercise here.
vi.mock('@/components/realm-theme-provider', () => ({
  useRealmTheme: () => ({ plainMode: false, setPlainMode: vi.fn() }),
}));
vi.mock('@/components/ConnectedAccounts', () => ({ ConnectedAccounts: () => null }));

import * as visibility from '@/roster/visibility';

function mockSettings(data: { appear_offline: boolean } | undefined, { isError = false } = {}) {
  vi.mocked(visibility.useVisibilitySettings).mockReturnValue({
    data,
    isLoading: false,
    isError,
  } as unknown as ReturnType<typeof visibility.useVisibilitySettings>);
}

function mockMutation(mutate = vi.fn()) {
  vi.mocked(visibility.useSetAppearOffline).mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof visibility.useSetAppearOffline>);
  return mutate;
}

describe('SettingsPage visibility toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the toggle unchecked when not hidden', () => {
    mockSettings({ appear_offline: false });
    mockMutation();
    render(<SettingsPage />);
    expect(screen.getByLabelText('Quiet (hidden) mode')).toHaveAttribute('aria-checked', 'false');
  });

  it('renders the toggle checked when hidden', () => {
    mockSettings({ appear_offline: true });
    mockMutation();
    render(<SettingsPage />);
    expect(screen.getByLabelText('Quiet (hidden) mode')).toHaveAttribute('aria-checked', 'true');
  });

  it('calls the mutation when toggled on', async () => {
    const user = userEvent.setup();
    mockSettings({ appear_offline: false });
    const mutate = mockMutation();
    render(<SettingsPage />);
    await user.click(screen.getByLabelText('Quiet (hidden) mode'));
    expect(mutate).toHaveBeenCalledWith(true);
  });

  it('shows a hint when no character is being played', () => {
    mockSettings(undefined, { isError: true });
    mockMutation();
    render(<SettingsPage />);
    expect(screen.getByTestId('visibility-no-character')).toBeInTheDocument();
  });
});
