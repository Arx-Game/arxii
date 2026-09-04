import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { ProfilePage } from './ProfilePage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

/** Mirror App.tsx: ProfilePage is the element of a `/profile/*` splat route. */
function renderAt(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/profile/*" element={<ProfilePage />}>
        <Route path="mail" element={<div>mail body</div>} />
        <Route path="media" element={<div>media body</div>} />
      </Route>
    </Routes>,
    { initialEntries: [path] }
  );
}

describe('ProfilePage', () => {
  it('defaults to mail tab when not on media path', () => {
    renderAt('/profile');
    expect(screen.getByRole('tab', { name: /mail/i })).toHaveAttribute('data-state', 'active');
  });

  it('selects media tab when on media path', () => {
    renderAt('/profile/media');
    expect(screen.getByRole('tab', { name: /media/i })).toHaveAttribute('data-state', 'active');
  });

  it('selects the account tab on /profile/account and links it absolutely', () => {
    renderAt('/profile/account');
    expect(screen.getByRole('tab', { name: /account/i })).toHaveAttribute('data-state', 'active');
    expect(screen.getByRole('tab', { name: /account/i })).toHaveAttribute(
      'href',
      '/profile/account'
    );
  });

  it('tab links stay anchored at /profile from inside a tab', () => {
    // React Router 7 resolves a relative link inside a splat route against the
    // full matched path, so `to="media"` at /profile/mail became /profile/mail/media
    // and every click appended another segment.
    renderAt('/profile/mail');
    expect(screen.getByRole('tab', { name: /media/i })).toHaveAttribute('href', '/profile/media');
    expect(screen.getByRole('tab', { name: /mail/i })).toHaveAttribute('href', '/profile/mail');
    expect(screen.getByRole('tab', { name: /muted/i })).toHaveAttribute('href', '/profile/mutes');
  });
});
