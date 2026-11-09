/**
 * StaffFamilyPage (#5039): the trail over the page links the realm's ladder.
 */
import { screen, within } from '@testing-library/react';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StaffFamilyPage } from '../family/StaffFamilyPage';
import type { FamilyDocument } from '../types';

const doc: FamilyDocument = {
  family: {
    id: 4,
    name: 'the Marrows',
    kind: 'Commoner',
    realm_id: 1,
    realm: 'Umbros',
    is_playable: false,
    description: '',
  },
  organization_id: null,
  tree: { family_id: 4, nodes: [], parentage: [], unions: [] },
  openings: { appable: [], posts: [], vacant_seats: [] },
};

vi.mock('../queries', () => ({
  useFamilyDocument: () => ({ data: doc }),
  useTemplates: () => ({ data: { results: [] } }),
  useAlmanachMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

test('the trail over the page: Almanach, the realm as a link, the family itself', () => {
  renderWithProviders(<StaffFamilyPage familyId={4} />);
  const trail = screen.getByRole('navigation', { name: 'Breadcrumb' });
  expect(within(trail).getByRole('link', { name: 'Almanach' })).toHaveAttribute(
    'href',
    '/staff/almanach'
  );
  expect(within(trail).getByRole('link', { name: 'Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/realms/1'
  );
  expect(within(trail).queryByRole('link', { name: 'the Marrows' })).toBeNull();
  expect(trail).toHaveTextContent('the Marrows');
});
