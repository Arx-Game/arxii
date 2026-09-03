import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AccountSettingsPage } from '../pages/AccountSettingsPage';

vi.mock('../components/EmailCard', () => ({ EmailCard: () => <div>email card</div> }));
vi.mock('../components/PasswordCard', () => ({ PasswordCard: () => <div>password card</div> }));
vi.mock('../components/TwoFactorCard', () => ({
  TwoFactorCard: () => <div>two factor card</div>,
}));
vi.mock('@/components/ConnectedAccounts', () => ({
  ConnectedAccounts: () => <div>connected accounts</div>,
}));

describe('AccountSettingsPage', () => {
  it('renders the email, password, two factor, and connected accounts cards in order', () => {
    render(<AccountSettingsPage />);
    const labels = screen.getAllByText(/card|connected accounts/i).map((el) => el.textContent);
    expect(labels).toEqual([
      'email card',
      'password card',
      'two factor card',
      'connected accounts',
    ]);
  });
});
