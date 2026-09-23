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
 *
 * Marisol's `believed_deceased: true` mirrors plate S-IV's own example (she
 * is publicly believed dead under her true name) and exercises the "hidden
 * truth" status text (review fix round 1, Finding I1) — the plate's own
 * wording for a row whose public record and truth diverge.
 */
import { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as queries from '../queries';
import { FamilyChapter } from '../document/FamilyChapter';
import type { AlmanachFamily, AlmanachHouseholdMember } from '../types';

// Spread the real `../queries` module and override only `useAllHouses`
// (mirrors `StoryAuthorTree.quickadd.test.tsx`'s importOriginal pattern) —
// `useGenders` keeps its real implementation, which resolves to an error
// state harmlessly in jsdom (no live server), exactly as it already did
// before this file mocked anything.
vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return { ...actual, useAllHouses: vi.fn() };
});

// Radix `Select` needs pointer-capture/portal machinery `userEvent` drives
// awkwardly in jsdom; swap it for a native `<select>` (mirrors
// `InsertLevelDialog.test.tsx`'s established mock shape) so AddKinDialog's
// "born into" pick can be driven with plain `selectOptions`. `id` is read
// off `SelectTrigger`'s own prop, same place the real component puts it, so
// `getByLabelText` still resolves through each field's own `<Label htmlFor>`.
vi.mock('@/components/ui/select', () => {
  function SelectTrigger({ children }: { children?: ReactNode }) {
    return <>{children}</>;
  }
  function Select({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (next: string) => void;
    children?: ReactNode;
  }) {
    let id: string | undefined;
    let options: ReactNode = null;
    Children.forEach(children, (child) => {
      if (!isValidElement(child)) return;
      if (child.type === SelectTrigger) {
        id = (child as ReactElement<{ id?: string }>).props.id;
      } else {
        options = child;
      }
    });
    return (
      <select id={id} value={value} onChange={(event) => onValueChange?.(event.target.value)}>
        {options}
      </select>
    );
  }
  return {
    Select,
    SelectTrigger,
    SelectValue: () => null,
    SelectContent: ({ children }: { children?: ReactNode }) => <>{children}</>,
    SelectItem: ({ value, children }: { value: string; children?: ReactNode }) => (
      <option value={value}>{children}</option>
    ),
  };
});

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
    believed_deceased: true,
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
  // The row's own status pill reads "hidden truth" for a concealed row
  // (plate S-IV), not the raw tier/household word, before any selection.
  expect(screen.getByText('hidden truth')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /marisol/i }));
  expect(screen.getByLabelText('deceased')).toBeInTheDocument();
  expect(screen.getByText('household · ward')).toBeInTheDocument();
  expect(screen.getByLabelText('known to the world as')).toBeInTheDocument();
});

test('the "born into" pick renders and its value reaches the create payload', async () => {
  // #3983 Task 10 fold-in: AddKinDialog's "born into" picker over
  // `useAllHouses()`, narrowed to rows with a `family_id` — this house has
  // one.
  vi.mocked(queries.useAllHouses).mockReturnValue({
    data: {
      results: [
        { id: 21, name: 'Ardor', house_state: 'standing', published_at: null, family_id: 4 },
      ],
    },
  } as never);
  const onCreate = vi.fn();
  renderWithProviders(
    <FamilyChapter
      houseId={9}
      houseName="Piropa"
      family={family}
      household={household}
      onEdit={() => {}}
      onCreate={onCreate}
    />
  );
  await userEvent.click(
    screen.getByRole('button', { name: /a person of the household · a position/i })
  );
  expect(screen.getByLabelText('born into')).toBeInTheDocument();
  expect(screen.getByRole('option', { name: 'Ardor' })).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('born into'), '4');
  await userEvent.type(screen.getByLabelText('name'), 'Tomas');
  await userEvent.click(screen.getByRole('button', { name: 'Add' }));
  expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ born_into_family_id: 4 }));
});
