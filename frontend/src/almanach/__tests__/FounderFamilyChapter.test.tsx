/**
 * FounderFamilyChapter + `familyShape.ts` (#3983 Plan B Task 5, plate F-III)
 * — `founderFamilyShape` turns head-relative `FounderKin` rows into the
 * `AlmanachFamily` shape `FamilyChapter`'s tree already knows how to
 * render; the rendered chapter shows the founder's own row as "your
 * character" and a deceased kin's row as "deceased".
 */
import { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import type { HouseTemplateOption } from '@/character-creation/api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FounderFamilyChapter } from '../founder/FounderFamilyChapter';
import {
  founderFamilyShape,
  FOUNDER_KIN_RELATIONS,
  FOUNDER_NODE_ID,
  HEAD_NODE_ID,
} from '../founder/familyShape';
import type { FounderDraft, FounderKin } from '../founder/founderDraft';

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return { ...actual, useAllHouses: vi.fn(() => ({ data: { results: [] } })) };
});

// Swap Radix `Select` for a native `<select>` (mirrors `FamilyChapter.test.
// tsx`'s own established mock) so the relation picker's actual OPTIONS can
// be inspected with `queryByRole('option', ...)` — `getByRole('combobox')`
// alone can't tell "head of house" was dropped from the list.
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

function kin(
  overrides: Partial<FounderKin> & Pick<FounderKin, 'key' | 'name' | 'relation'>
): FounderKin {
  return {
    gender_id: null,
    age: null,
    is_deceased: false,
    born_into_id: null,
    born_into_name: '',
    is_household: false,
    ...overrides,
  };
}

function baseDraft(kinRows: FounderKin[]): FounderDraft {
  return {
    realm_id: 1,
    title_id: 12,
    template_id: 3,
    house_name: 'Candela',
    words: '',
    colors: '',
    sigil_description: '',
    backstory: '',
    aspect_picks: {},
    principles: {},
    founder_relation: 'child',
    founder_is_heir: true,
    kin: kinRows,
    lands: {},
    estate_name: '',
    estate_description: '',
  };
}

const headMotherSpouse = () => [
  kin({ key: 'head', name: 'Estuosa', relation: 'head' }),
  kin({ key: 'mother', name: 'Fiamma', relation: 'mother', is_deceased: true }),
  kin({ key: 'spouse', name: 'Dario', relation: 'spouse' }),
];

/** A fixture with no spouse, for tests that don't need the full
 * head+mother+spouse scenario (the "family you may define" count). */
const headMotherOnly = () => [
  kin({ key: 'head', name: 'Estuosa', relation: 'head' }),
  kin({ key: 'mother', name: 'Fiamma', relation: 'mother', is_deceased: true }),
];

test('the shape for head + mother + spouse + founder(child) yields the expected edges', () => {
  const draft = baseDraft(headMotherSpouse());
  const shape = founderFamilyShape(draft, 'Marisol');

  // Kin ids are assigned in draft order, head reserving -1 and the rest
  // counting down from -3 — mother (the second kin row) is -3, spouse
  // (the third) is -4.
  const motherId = -3;
  const spouseId = -4;

  expect(shape.family.parentage).toEqual([
    {
      child_id: HEAD_NODE_ID,
      parent_id: motherId,
      kind: 'biological',
      is_true: true,
      via_secret: false,
    },
    {
      child_id: FOUNDER_NODE_ID,
      parent_id: HEAD_NODE_ID,
      kind: 'biological',
      is_true: true,
      via_secret: false,
    },
    {
      child_id: FOUNDER_NODE_ID,
      parent_id: spouseId,
      kind: 'biological',
      is_true: true,
      via_secret: false,
    },
  ]);
  expect(shape.family.unions).toEqual([
    { id: spouseId, kind: 'marriage', member_ids: [HEAD_NODE_ID, spouseId], ended: false },
  ]);
  expect(shape.keyByNodeId[motherId]).toBe('mother');
  expect(shape.keyByNodeId[HEAD_NODE_ID]).toBe('head');
});

test('the rendered tree shows "your character" on the founder row and the mother\'s "deceased" status', () => {
  const { container } = renderWithProviders(
    <FounderFamilyChapter
      draft={baseDraft(headMotherSpouse())}
      set={vi.fn()}
      addKin={vi.fn()}
      updateKin={vi.fn()}
      removeKin={vi.fn()}
      template={{ id: 3 } as HouseTemplateOption}
      youName="Marisol"
      onNext={vi.fn()}
    />
  );

  expect(screen.getByText('your character')).toBeInTheDocument();
  expect(screen.getByText('deceased')).toBeInTheDocument();
  // The founder plate's own relation vocabulary, not `FamilyChapter`'s
  // structural depth-based words.
  expect(screen.getByText('head of house')).toBeInTheDocument();
  // I3 — the founder's own `.rel` carries her relation word too, not just
  // her place in the line.
  expect(screen.getByText('child · heir')).toBeInTheDocument();

  // I1 (fix round 1) — head + spouse (union) + founder(child, edges to
  // both) renders the founder exactly once, and the spouse nests beside
  // the head as a consort rather than becoming a spurious second root:
  // Fiamma (the head's own mother) is the tree's only root, Estuosa nests
  // as her child, and Dario is never a second top-level entry.
  expect(screen.getAllByText('Marisol')).toHaveLength(1);
  const topLevelNames = Array.from(container.querySelectorAll('.tree > li > .who .nm')).map(
    (el) => el.textContent
  );
  expect(topLevelNames).toEqual(['Fiamma']);
});

test('the founder relation dialog never offers grandparent', () => {
  expect(FOUNDER_KIN_RELATIONS).not.toContain('grandparent');
  expect(FOUNDER_KIN_RELATIONS).toEqual(
    expect.arrayContaining([
      'head',
      'mother',
      'father',
      'spouse',
      'sibling',
      'child',
      'ward',
      'position',
    ])
  );
});

test('the "family you may define" row falls back to the named kin count', () => {
  renderWithProviders(
    <FounderFamilyChapter
      draft={baseDraft(headMotherOnly())}
      set={vi.fn()}
      addKin={vi.fn()}
      updateKin={vi.fn()}
      removeKin={vi.fn()}
      // No `starting_kin_slots` on the wire yet (`HouseTemplateOption`,
      // `src/generated/api.d.ts`) — the bare kin count is the honest
      // fallback rather than a fabricated "X of Y" fraction.
      template={{ id: 3 } as HouseTemplateOption}
      youName="Marisol"
      onNext={vi.fn()}
    />
  );

  const defineField = screen.getByText('family you may define').closest('.field');
  expect(defineField).toHaveTextContent('2');
  const onRecordField = screen.getByText('on record').closest('.field');
  expect(onRecordField).toHaveTextContent('3');
});

// C1 (fix round 1) — "at most one head": the option drops out of the
// dialog's own relation `<select>` the moment a second one would orphan the
// founder's own placement, whether she occupies the head slot herself or a
// separate head kin row is already on record.
test('the relation dialog hides "head of house" once the founder occupies the head', async () => {
  renderWithProviders(
    <FounderFamilyChapter
      draft={{ ...baseDraft([]), founder_relation: 'head' }}
      set={vi.fn()}
      addKin={vi.fn()}
      updateKin={vi.fn()}
      removeKin={vi.fn()}
      template={{ id: 3 } as HouseTemplateOption}
      youName="Marisol"
      onNext={vi.fn()}
    />
  );

  await userEvent.click(screen.getByRole('button', { name: '⊕ a sibling · a spouse' }));
  const relationSelect = screen.getByLabelText('relation');
  expect(
    within(relationSelect).queryByRole('option', { name: 'head of house' })
  ).not.toBeInTheDocument();
  expect(within(relationSelect).getByRole('option', { name: 'mother' })).toBeInTheDocument();
});

test('the relation dialog hides "head of house" once a head kin row already exists', async () => {
  renderWithProviders(
    <FounderFamilyChapter
      draft={baseDraft(headMotherOnly())}
      set={vi.fn()}
      addKin={vi.fn()}
      updateKin={vi.fn()}
      removeKin={vi.fn()}
      template={{ id: 3 } as HouseTemplateOption}
      youName="Marisol"
      onNext={vi.fn()}
    />
  );

  await userEvent.click(screen.getByRole('button', { name: '⊕ a sibling · a spouse' }));
  const relationSelect = screen.getByLabelText('relation');
  expect(
    within(relationSelect).queryByRole('option', { name: 'head of house' })
  ).not.toBeInTheDocument();
  expect(within(relationSelect).getByRole('option', { name: 'sibling' })).toBeInTheDocument();
});
