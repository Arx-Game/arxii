/**
 * FrontPage (#4239): the three rolls with a search each, the three Create
 * buttons, and the Commoner roll narrowing to the search.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FrontPage } from '../front/FrontPage';

const all = {
  noble: [{ kind: 'realm', id: 1, name: 'Umbros', titles: 3, held: 2, unclaimed: 1 }],
  crime: [{ kind: 'city', id: 7, name: 'Arx', families: 1, gangs: 2, crew_slots: 3 }],
  commoner: [
    { kind: 'family', id: 4, name: 'Teale', sub: 'commoner', on_record: 9, appable: 2 },
    { kind: 'family', id: 5, name: 'Varrow', sub: 'merchant', on_record: 4, appable: 0 },
  ],
};
const narrowed = { ...all, commoner: [all.commoner[0]] };

vi.mock('../queries', () => ({
  useFront: (q: string) => ({ data: q === 'tea' ? narrowed : all }),
  useSearch: () => ({ data: undefined }),
  useRealms: () => ({ data: { results: [{ id: 1, name: 'Umbros' }] } }),
  useFamilyKinds: () => ({ data: { results: [] } }),
  useTemplates: () => ({ data: { results: [] } }),
  useRealmTitles: () => ({ data: { results: [] } }),
  useVacantTitles: () => ({ data: { results: [] } }),
  useAlmanachMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

test('three rolls, three Create buttons, and the realm opens its ladder', () => {
  renderWithProviders(<FrontPage />);
  expect(screen.getByRole('heading', { name: 'Noble' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Crime' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Commoner' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create Domain' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create Family' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create Kin' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/realms/1'
  );
  expect(screen.getByText('3 titles · 2 held · 1 unclaimed')).toBeInTheDocument();
  expect(screen.getByText('1 family · 2 gangs · 3 crew slots')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Teale' })).toHaveAttribute(
    'href',
    '/staff/almanach/families/4'
  );
  expect(screen.getByText('commoner · 9 on record · 2 appable')).toBeInTheDocument();
});

test("typing in the Commoner roll's search narrows that roll only", async () => {
  renderWithProviders(<FrontPage />);
  await userEvent.type(screen.getByRole('searchbox', { name: 'Search commoner' }), 'tea');
  const commoner = screen.getByRole('heading', { name: 'Commoner' }).closest('section')!;
  expect(within(commoner).getByText('Teale')).toBeInTheDocument();
  expect(within(commoner).queryByText('Varrow')).toBeNull();
  expect(screen.getByRole('link', { name: 'Umbros' })).toBeInTheDocument();
});

test('Create Family opens the form with family type, name, realm and holding', async () => {
  renderWithProviders(<FrontPage />);
  await userEvent.click(screen.getByRole('button', { name: 'Create Family' }));
  const form = screen.getByRole('form', { name: 'Create Family' });
  expect(within(form).getByLabelText('family type')).toBeInTheDocument();
  expect(within(form).getByLabelText('name')).toBeInTheDocument();
  expect(within(form).getByLabelText('realm')).toBeInTheDocument();
  expect(within(form).getByRole('button', { name: 'None yet' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
});
