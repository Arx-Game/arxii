import { act, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Footer } from './Footer';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';

describe('Footer', () => {
  afterEach(() => {
    act(() => {
      store.dispatch(setAccount(null));
    });
  });

  it('offers Log in to a guest', () => {
    store.dispatch(setAccount(null));
    renderWithProviders(<Footer />);

    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
  });

  // #5207: a signed-in player saw "Log in" at the foot of every page.
  it('does not offer Log in to a signed-in player', () => {
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<Footer />);

    expect(screen.queryByRole('link', { name: 'Log in' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Codex' })).toBeInTheDocument();
  });
});
