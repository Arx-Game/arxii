/**
 * Crumbs (#5039): the trail over an Almanach page. Every step with a destination
 * is a link; the last step is the page itself and never one.
 */
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { Crumbs } from '../shared/Crumbs';

test('every step but the last is a link to its destination', () => {
  renderWithProviders(
    <Crumbs
      trail={[
        { label: 'Almanach', to: '/staff/almanach' },
        { label: 'Umbros', to: '/staff/almanach/realms/1' },
        { label: 'Duchy of Katta', to: '/staff/almanach/titles/3' },
      ]}
    />
  );
  const nav = screen.getByRole('navigation', { name: 'Breadcrumb' });
  expect(screen.getByRole('link', { name: 'Almanach' })).toHaveAttribute('href', '/staff/almanach');
  expect(screen.getByRole('link', { name: 'Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/realms/1'
  );
  expect(screen.queryByRole('link', { name: 'Duchy of Katta' })).toBeNull();
  expect(nav).toHaveTextContent('Duchy of Katta');
});

test('a step with no destination is plain text', () => {
  renderWithProviders(<Crumbs trail={[{ label: 'Staff' }, { label: 'Almanach de Catenys' }]} />);
  expect(screen.queryAllByRole('link')).toHaveLength(0);
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent(
    'StaffAlmanach de Catenys'
  );
});
