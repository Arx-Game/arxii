/**
 * FamilyChapter (#3983 Task 9) — selecting a household member opens
 * `PersonPanel` in place with the deceased toggle and the belief fields.
 *
 * `family` is shaped after `FamilyTreePayload`
 * (`world/roster/services/kinship.py:761`, mirrored by `AlmanachFamily`,
 * `types.ts`): `nodes`/`parentage`/`unions`, not the sketch's `edges`.
 * Marisol is a pure household holder (`household[]`, `AlmanachHouseholdMember`)
 * rather than a tree node with `relation`/`is_household`/`born_into` fields
 * — those don't exist on the wire; a household row's own `position` is what
 * `PersonPanel`'s "in the house as" field reads (`household · <position>`).
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FamilyChapter } from '../document/FamilyChapter';
import type { AlmanachFamily, AlmanachHouseholdMember } from '../types';

const family: AlmanachFamily = {
  nodes: [
    {
      id: 1,
      name: 'Galerna aza Piropa',
      tier: 'standing',
      family_id: 1,
      is_deceased: false,
      is_appable: false,
      sheet_id: null,
      gender: 'Woman',
      age: 45,
      description: '',
      believed_deceased: false,
    },
  ],
  parentage: [],
  unions: [],
};

const household: AlmanachHouseholdMember[] = [
  {
    vacancy_id: 5,
    position: 'ward',
    holder_id: 2,
    holder_name: 'Marisol',
    is_open: false,
    count_remaining: 0,
    is_deceased: false,
    believed_deceased: false,
  },
];

test('selecting a person opens the panel in place with belief fields', async () => {
  renderWithProviders(
    <FamilyChapter
      houseId={9}
      houseName="Piropa"
      family={family}
      household={household}
      onEdit={() => {}}
    />
  );
  await userEvent.click(screen.getByRole('button', { name: /marisol/i }));
  expect(screen.getByLabelText('deceased')).toBeInTheDocument();
  expect(screen.getByText('household · ward')).toBeInTheDocument();
  expect(screen.getByLabelText('known to the world as')).toBeInTheDocument();
});
