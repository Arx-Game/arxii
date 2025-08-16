import { screen } from '@testing-library/react';
import { ProfilePage } from './ProfilePage';
import { renderWithProviders } from '../test/utils/renderWithProviders';

describe('ProfilePage', () => {
  it('defaults to mail tab when not on media path', () => {
    renderWithProviders(<ProfilePage />, { initialEntries: ['/profile'] });
    expect(screen.getByRole('tab', { name: /mail/i })).toHaveAttribute('data-state', 'active');
  });

  it('selects media tab when on media path', () => {
    renderWithProviders(<ProfilePage />, { initialEntries: ['/profile/media'] });
    expect(screen.getByRole('tab', { name: /media/i })).toHaveAttribute('data-state', 'active');
  });
});
