/**
 * PersonPage (#4239): the tier spelled long after the name, (RIP) in the muted
 * mark, kin names as links, Create Family for <name> dispatching with the
 * person as holder, and a PC's name read-only.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PersonPage } from '../person/PersonPage';
import type { PersonDocument } from '../types';

const mutateAsync = vi
  .fn()
  .mockResolvedValue({ success: true, data: { family_id: 1, org_id: 2, title_id: 3 } });
const mutate = vi.fn();

const doc: PersonDocument = {
  person: {
    id: 11,
    name: 'Kathryn mar Katta',
    display_name: 'Kathryn mar Katta',
    gender_id: null,
    gender: '',
    age: 24,
    tier: 'standing',
    tier_display: { number: 2, label: 'Standing NPC' },
    status: 'alive',
    record_accurate: true,
    obituary: '',
    is_pc: false,
    description: '',
  },
  family: null,
  kin: [
    {
      id: 12,
      name: 'Father mar Katta',
      relation: 'parent',
      tier: 'name_only',
      tier_display: { number: 0, label: 'Offscreen Reference' },
      status: 'rip',
      is_pc: false,
      sheet_id: null,
      is_appable: false,
      family_id: 1,
    },
    {
      id: 13,
      name: 'Sister mar Katta',
      relation: 'sibling',
      tier: 'name_only',
      tier_display: { number: 0, label: 'Offscreen Reference' },
      status: 'alive',
      is_pc: false,
      sheet_id: null,
      is_appable: true,
      family_id: 1,
    },
  ],
  house: null,
  titles: [],
  sheet: {
    sheet_id: null,
    is_appable: false,
    name_locked: false,
    age_min: null,
    age_max: null,
    allowed_gender_ids: [],
  },
  memberships: [],
  record: { parents: 1, children: 0, siblings: 1, unions: 0, hidden_truths: 0 },
};
let mockDoc: PersonDocument = doc;

vi.mock('../queries', () => ({
  usePersonDocument: () => ({ data: mockDoc }),
  useGenders: () => ({ data: [] }),
  useUnionKinds: () => ({
    data: { results: [{ id: 1, name: 'Marriage', confers_wedlock: true }] },
  }),
  useSearch: () => ({ data: undefined }),
  useRealms: () => ({ data: { results: [{ id: 1, name: 'Umbros' }] } }),
  useFamilyKinds: () => ({
    data: { results: [{ id: 9, name: 'Noble', styles_as_house: true, sort_order: 0 }] },
  }),
  useTemplates: () => ({ data: { results: [{ id: 5, name: 'Umbral noble house' }] } }),
  useRealmTitles: () => ({ data: { results: [] } }),
  useVacantTitles: () => ({ data: { results: [] } }),
  useAlmanachMutation: () => ({ mutate, mutateAsync }),
}));

test('tier reads long after the name, kin are links, the dead carry (RIP)', () => {
  renderWithProviders(<PersonPage personId={11} />);
  const heading = screen.getByRole('heading', { level: 3 });
  expect(heading).toHaveTextContent('Kathryn mar Katta');
  expect(heading).toHaveTextContent('(Standing NPC)');
  expect(screen.getByRole('link', { name: 'Father mar Katta' })).toHaveAttribute(
    'href',
    '/staff/almanach/people/12'
  );
  const father = screen.getByRole('link', { name: 'Father mar Katta' }).closest('li')!;
  expect(within(father).getByText('(RIP)')).toHaveClass('gone');
  expect(within(father).queryByText(/strike|†/)).toBeNull();
  const sister = screen.getByRole('link', { name: 'Sister mar Katta' }).closest('li')!;
  expect(within(sister).getByText('appable')).toBeInTheDocument();
  const tierSeg = screen.getByRole('group', { name: 'NPC tier' });
  expect(within(tierSeg).getByRole('button', { name: '2' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(within(tierSeg).getByRole('button', { name: '1' })).toBeDisabled();
  expect(within(tierSeg).getByRole('button', { name: '3' })).not.toBeDisabled();
});

test('Create Family for the person dispatches with them as holder', async () => {
  renderWithProviders(<PersonPage personId={11} />);
  await userEvent.click(
    screen.getByRole('button', { name: 'Create Family for Kathryn mar Katta' })
  );
  const form = screen.getByRole('form', { name: 'Create Family for Kathryn mar Katta' });
  await userEvent.clear(within(form).getAllByLabelText('name')[0]);
  await userEvent.type(within(form).getAllByLabelText('name')[0], 'Katta');
  expect(
    within(form).getByRole('button', { name: 'Create Family for Kathryn mar Katta' })
  ).toBeDisabled();
  await userEvent.type(within(form).getAllByLabelText('name')[1], 'Duchy of Katta');
  await userEvent.click(
    within(form).getByRole('button', { name: 'Create Family for Kathryn mar Katta' })
  );
  expect(mutateAsync).toHaveBeenCalledWith(
    expect.objectContaining({
      kind_id: 9,
      name: 'Katta',
      holding: 'create',
      title_tier: 'county',
      title_name: 'Duchy of Katta',
      holder_id: 11,
      template_id: 5,
    })
  );
});

test("a player character's name is read-only and the tier seg is locked", () => {
  mockDoc = {
    ...doc,
    person: {
      ...doc.person,
      tier: 'pc',
      tier_display: { number: null, label: 'Player Character' },
      is_pc: true,
    },
  };
  try {
    renderWithProviders(<PersonPage personId={11} />);
    expect(screen.getByLabelText('name')).toHaveAttribute('readonly');
    const tierSeg = screen.getByRole('group', { name: 'NPC tier' });
    for (const n of ['0', '1', '2', '3']) {
      expect(within(tierSeg).getByRole('button', { name: n })).toBeDisabled();
    }
  } finally {
    mockDoc = doc;
  }
});
