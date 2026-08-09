import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '@/staff/api';
import type { AccountInvite } from '@/staff/types';
import { StaffInvitesPage } from './StaffInvitesPage';

vi.mock('@/staff/api');
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeInvite(overrides: Partial<AccountInvite> = {}): AccountInvite {
  return {
    id: 1,
    email: 'invitee@example.com',
    token: 'abc123',
    status: 'pending',
    note: '',
    created_at: '2026-08-08T00:00:00Z',
    expires_at: '2026-09-07T00:00:00Z',
    redeemed_at: null,
    revoked_at: null,
    invited_by: 1,
    invited_by_username: 'staffer',
    redeemed_by: null,
    redeemed_by_username: null,
    ...overrides,
  };
}

describe('StaffInvitesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('lists existing invites', async () => {
    vi.mocked(api.getAccountInviteList).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeInvite()],
    });

    renderWithProviders(<StaffInvitesPage />);

    expect(await screen.findByText('invitee@example.com')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('shows an empty state when there are no invites', async () => {
    vi.mocked(api.getAccountInviteList).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    renderWithProviders(<StaffInvitesPage />);

    expect(await screen.findByText(/no invites found/i)).toBeInTheDocument();
  });

  it('issues a new invite', async () => {
    vi.mocked(api.getAccountInviteList).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(api.issueAccountInvite).mockResolvedValue(makeInvite());

    renderWithProviders(<StaffInvitesPage />);

    await screen.findByText(/no invites found/i);
    await userEvent.type(screen.getByLabelText('Email'), 'invitee@example.com');
    await userEvent.click(screen.getByRole('button', { name: /issue invite/i }));

    await waitFor(() => {
      expect(api.issueAccountInvite).toHaveBeenCalledWith('invitee@example.com', '');
    });
  });

  it('revokes a pending invite', async () => {
    vi.mocked(api.getAccountInviteList).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeInvite()],
    });
    vi.mocked(api.revokeAccountInvite).mockResolvedValue(makeInvite({ status: 'revoked' }));

    renderWithProviders(<StaffInvitesPage />);

    await screen.findByText('invitee@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }));

    await waitFor(() => {
      expect(api.revokeAccountInvite).toHaveBeenCalledWith(1);
    });
  });
});
