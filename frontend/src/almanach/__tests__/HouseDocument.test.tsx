/**
 * HouseDocument (#3983 Task 9) — smoke test: it opens on The House with the
 * contents rail (House/Family, Realm/Lands/Estate) and the record rail
 * around it, and the particle field shows the house's own pair.
 * Plus final review I11/deferred item 3: `realm.realm_theme` gates the
 * Gentry toggle, `realm.default_tithe_pct` prefills the swear dialog's
 * tithe, and `realm.realm_id` makes "the ladder" record door a real link.
 *
 * The `doc` fixture is shaped after the REAL wire types (`HouseDocument`,
 * `types.ts`) — `default_succession_law` (not the sketch's `succession`),
 * `estate: []` (a list, never `null` — `_estate_payload` always returns a
 * list), `lands.baronies[].id` (not `domain_id`).
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as queries from '../queries';
import { HouseDocument } from '../document/HouseDocument';
import type { HouseDocument as HouseDocumentPayload } from '../types';

vi.mock('../queries');

const doc: HouseDocumentPayload = {
  house: {
    id: 9,
    name: 'Piropa',
    description: '',
    words: '',
    colors: '',
    sigil_description: '',
    house_state: 'standing',
    published_at: null,
    particle: { born: 'aza', taken_in: 'azas' },
    default_succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: null },
    patron: { being_id: 31, being_name: 'Calyx', codex_entry_id: 77 },
    facets: [
      {
        definition: 'Patron',
        definition_id: 3,
        option: 'Calyx',
        option_id: 31,
        description: 'The knight who kept the first vigil.',
        being_name: 'Calyx',
        target_entry_id: 77,
      },
    ],
    charter_questions: [],
    features: [],
    offices: [],
    observances: [
      { ic_month: 10, ic_day: 18, name: 'Founding Night', lore: '', when: 'Masquing 18 (10/18)' },
    ],
  },
  family: { family_id: 4, nodes: [], parentage: [], unions: [] },
  household: [],
  realm: {
    sworn_to: '',
    obligation_pct: null,
    holds: 'Inferna',
    demesne: [],
    vassals: [],
    realm_id: 1,
    default_tithe_pct: 10,
    realm_theme: '',
  },
  lands: {
    count: 1,
    population: 0,
    produces: [],
    seat: 'Perdition',
    baronies: [
      {
        id: 3,
        name: 'Perdition',
        in: 'County of Inferna',
        hall: 'the Palazzo Ardente',
        is_seat: true,
        description: '',
        land_shapes: [],
        population: 0,
      },
    ],
  },
  estate: [],
  books: { income_week: 0, uncollected: 0, treasury: 0, streams: 0 },
  forces: [],
  openings: { appable: [], posts: [], vacant_seats: [] },
  turf: null,
};

test('opens on The House with the contents rail and the record rail', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByRole('heading', { name: /house piropa/i })).toBeInTheDocument();
  expect(screen.getByText('The Family')).toBeInTheDocument();
  expect(screen.getByText('Lands')).toBeInTheDocument();
  // The particles themselves, born then taken-in, with nothing to hover (#5090).
  expect(screen.getByText('aza / azas')).toBeInTheDocument();
  expect(screen.queryByText(/worked example/i)).not.toBeInTheDocument();
  // The record rail (aside.record) opens alongside The House.
  expect(screen.getByText('on record')).toBeInTheDocument();
});

test('the state control calls a house in its normal state Active (#5090)', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  const state = screen.getByLabelText('State') as HTMLSelectElement;
  expect(state.value).toBe('standing');
  expect(state.selectedOptions[0]).toHaveTextContent('Active');
  expect(screen.queryByRole('option', { name: 'Standing' })).not.toBeInTheDocument();
});

test('the record links are named for where they go, and the family page link works (#5090)', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByRole('link', { name: 'Piropa org page' })).toHaveAttribute('href', '/orgs/9');
  expect(screen.getByRole('link', { name: 'Piropa family page' })).toHaveAttribute(
    'href',
    '/families/4'
  );
  expect(screen.queryByText(/house on the roster/i)).not.toBeInTheDocument();
  expect(screen.queryByText('the organization')).not.toBeInTheDocument();
});

test('the record rail draws no row or link the document has nothing for (#5090)', async () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.queryByText('stature')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'The Family' }));
  for (const gone of ['kin slots', 'influence', 'recognition', 'linked houses', /the secret/]) {
    expect(screen.queryByText(gone)).not.toBeInTheDocument();
  }
  expect(screen.getByRole('link', { name: 'Piropa family page' })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'Titles' }));
  for (const gone of ['treasury', 'pacts']) {
    expect(screen.queryByText(gone)).not.toBeInTheDocument();
  }
  expect(screen.getByRole('link', { name: 'the ladder' })).toBeInTheDocument();
});

test('a house with no family has no family page link (#5090)', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: { ...doc, family: { ...doc.family, family_id: null } },
    isLoading: false,
  } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByRole('link', { name: 'Piropa org page' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /family page/i })).not.toBeInTheDocument();
});

test('Gentry toggles like any other state when the realm theme is luxen', async () => {
  const mutate = vi.fn();
  vi.mocked(queries.useAlmanachMutation).mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
  } as never);
  const luxenDoc: HouseDocumentPayload = {
    ...doc,
    realm: { ...doc.realm, realm_theme: 'luxen' },
  };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: luxenDoc,
    isLoading: false,
  } as never);

  renderWithProviders(<HouseDocument houseId={9} />);
  const state = screen.getByRole('combobox', { name: 'State' });
  const gentry = screen.getByRole('option', { name: 'Gentry' });
  expect(gentry).not.toBeDisabled();
  await userEvent.selectOptions(state, 'gentry');
  expect(state).toHaveValue('gentry');

  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, house_state: 'gentry' });
});

test('a house with no charter answers shows no Quiddity heading, and answers group under their question (#4533)', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  const { unmount } = renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByText('Patron')).toBeInTheDocument();
  expect(screen.queryByText(/House Quiddity/)).not.toBeInTheDocument();
  unmount();

  const umbralDoc: HouseDocumentPayload = { ...doc, house: { ...doc.house, facets: [] } };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: umbralDoc,
    isLoading: false,
  } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.queryByText(/Quiddity/)).not.toBeInTheDocument();
  expect(screen.queryByText('Patron')).not.toBeInTheDocument();
});

const QUIDDITY = {
  id: 1,
  name: 'House Quiddity',
  prompt: 'What drives your house?',
  min_picks: 1,
  max_picks: 1,
  sets_patron: false,
  options: [
    { id: 11, name: 'Glamour', description: 'Beauty as a weapon.', target_entry_id: 23 },
    { id: 12, name: 'Vendetta', description: 'A grudge kept warm.', target_entry_id: 29 },
  ],
};
const VICES = {
  id: 2,
  name: 'House Vices',
  prompt: 'Which two?',
  min_picks: 0,
  max_picks: 2,
  sets_patron: false,
  options: [
    { id: 21, name: 'Greed', description: '', target_entry_id: null },
    { id: 22, name: 'Envy', description: '', target_entry_id: null },
    { id: 23, name: 'Sloth', description: '', target_entry_id: null },
  ],
};

test("a single-pick charter question is a select; saving sends the house's whole facet list (#5064)", async () => {
  const mutate = vi.fn();
  vi.mocked(queries.useAlmanachMutation).mockReturnValue({ mutate, mutateAsync: vi.fn() } as never);
  const infernal: HouseDocumentPayload = {
    ...doc,
    house: {
      ...doc.house,
      facets: [
        {
          definition: 'House Quiddity',
          definition_id: 1,
          option: 'Vendetta',
          option_id: 12,
          description: 'A grudge kept warm.',
          being_name: '',
          target_entry_id: 29,
        },
      ],
      charter_questions: [QUIDDITY],
    },
  };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: infernal,
    isLoading: false,
  } as never);

  renderWithProviders(<HouseDocument houseId={9} />);
  const picker = screen.getByRole('combobox', { name: 'House Quiddity' });
  expect(picker).toHaveValue('12');
  expect(screen.getByRole('link', { name: 'Vendetta' })).toHaveAttribute('href', '/codex?entry=29');
  await userEvent.selectOptions(picker, '11');
  expect(screen.getByRole('link', { name: 'Glamour' })).toHaveAttribute('href', '/codex?entry=23');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, facet_option_ids: [11] });
});

test('a several-pick question is pressed chips capped at its maximum, and a pick on another question rides along (#5064)', async () => {
  const mutate = vi.fn();
  vi.mocked(queries.useAlmanachMutation).mockReturnValue({ mutate, mutateAsync: vi.fn() } as never);
  const infernal: HouseDocumentPayload = {
    ...doc,
    house: {
      ...doc.house,
      facets: [
        {
          definition: 'House Quiddity',
          definition_id: 1,
          option: 'Glamour',
          option_id: 11,
          description: 'Beauty as a weapon.',
          being_name: '',
          target_entry_id: 23,
        },
      ],
      charter_questions: [QUIDDITY, VICES],
    },
  };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: infernal,
    isLoading: false,
  } as never);

  renderWithProviders(<HouseDocument houseId={9} />);
  const vices = screen.getByRole('group', { name: 'House Vices' });
  await userEvent.click(within(vices).getByRole('button', { name: 'Greed' }));
  await userEvent.click(within(vices).getByRole('button', { name: 'Envy' }));
  await userEvent.click(within(vices).getByRole('button', { name: 'Sloth' }));
  expect(within(vices).getByRole('button', { name: 'Greed' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(within(vices).getByRole('button', { name: 'Envy' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(within(vices).getByRole('button', { name: 'Sloth' })).toHaveAttribute(
    'aria-pressed',
    'false'
  );
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, facet_option_ids: [11, 21, 22] });
});

test("the patron reads by the god's own name and opens its page (#4205, #5110)", () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: doc,
    isLoading: false,
  } as never);

  renderWithProviders(<HouseDocument houseId={9} />);
  // This house's realm asks no patron question, so the patron has its own line.
  const patron = screen.getByText('patron').closest('.field') as HTMLElement;
  expect(within(patron).getByRole('link', { name: 'Calyx' })).toHaveAttribute(
    'href',
    '/codex?entry=77'
  );
  expect(screen.queryByText(/The One True Knight/)).not.toBeInTheDocument();
});

test('the patron question is a select of gods, and its pick is saved as the patron (#5110)', async () => {
  const mutate = vi.fn();
  vi.mocked(queries.useAlmanachMutation).mockReturnValue({ mutate } as never);
  const patronQuestion = {
    id: 3,
    name: 'Umbral Patron Deity',
    prompt: 'Whom does the house stand behind?',
    min_picks: 1,
    max_picks: 1,
    sets_patron: true,
    options: [
      { id: 31, name: 'Calyx', description: 'Honorable combat', target_entry_id: 77 },
      { id: 32, name: 'Veil', description: 'Secrets kept', target_entry_id: 78 },
    ],
  };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: {
      ...doc,
      house: { ...doc.house, facets: [], charter_questions: [patronQuestion] },
    },
    isLoading: false,
  } as never);
  renderWithProviders(<HouseDocument houseId={9} />);

  // The house's patron is what the select starts on; no separate patron line.
  const select = screen.getByLabelText('Umbral Patron Deity') as HTMLSelectElement;
  expect(select.value).toBe('31');
  expect(screen.queryByText('patron')).not.toBeInTheDocument();
  expect(
    within(select)
      .getAllByRole('option')
      .map((o) => o.textContent)
  ).toEqual(['pick', 'Calyx', 'Veil']);

  await userEvent.selectOptions(select, '32');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  // A god, sent on its own: never among the option ids.
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, patron_being_id: 32 });

  mutate.mockClear();
  await userEvent.selectOptions(select, '');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, patron_being_id: null });
});

test('editing a day of remembrance saves the whole list, without the spelled date (#4206)', async () => {
  const mutate = vi.fn();
  vi.mocked(queries.useAlmanachMutation).mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
  } as never);
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: doc,
    isLoading: false,
  } as never);

  renderWithProviders(<HouseDocument houseId={9} />);
  const name = screen.getByLabelText('name', { selector: '#house-9-observance-0-name' });
  expect(name).toHaveValue('Founding Night');
  await userEvent.click(screen.getByRole('button', { name: 'Add a day of remembrance' }));
  await userEvent.type(
    screen.getByLabelText('name', { selector: '#house-9-observance-1-name' }),
    'The Vigil'
  );

  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({
    org_id: 9,
    observances: [
      { ic_month: 10, ic_day: 18, name: 'Founding Night', lore: '' },
      { ic_month: 1, ic_day: 1, name: 'The Vigil', lore: '' },
    ],
  });
});

test('Gentry stays disabled ("Luxen only") when the realm theme is not luxen', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  const gentry = screen.getByRole('option', { name: 'Gentry' });
  expect(gentry).toBeDisabled();
  expect(gentry).toHaveAttribute('title', 'Luxen only');
});

test("the ladder record door links to the realm's own ladder page when realm_id is set", async () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Titles' }));
  const door = screen.getByRole('link', { name: 'the ladder' });
  expect(door).toHaveAttribute('href', '/staff/almanach/realms/1');
});

test("the ladder record door is absent when the house's realm carries no id", async () => {
  const noRealmIdDoc: HouseDocumentPayload = { ...doc, realm: { ...doc.realm, realm_id: null } };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: noRealmIdDoc,
    isLoading: false,
  } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Titles' }));
  expect(screen.queryByText('the ladder')).not.toBeInTheDocument();
});

test('swearing a house prefills the tithe percent from the realm default', async () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Titles' }));
  await userEvent.click(screen.getByRole('button', { name: 'Swear a house' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByLabelText('tithe percent')).toHaveValue(10);
});

test('sigil is two rows without a handle, description is six, and the savebar carries only Save (#4549)', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  const sigil = screen.getByLabelText('sigil');
  expect(sigil).toHaveAttribute('rows', '2');
  expect(sigil).toHaveClass('prose', 'short');
  const description = screen.getByLabelText('description');
  expect(description).toHaveAttribute('rows', '6');
  expect(description).not.toHaveClass('short');
  expect(screen.queryByText('draft kept as you type')).not.toBeInTheDocument();
  const save = screen.getByRole('button', { name: 'Save' });
  expect(save.parentElement?.children).toHaveLength(1);
});

test('a house whose name already says House is not headed House House (#4549)', () => {
  const named: HouseDocumentPayload = { ...doc, house: { ...doc.house, name: 'House Katta' } };
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: named, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByRole('heading', { name: 'House Katta' })).toBeInTheDocument();
  expect(screen.queryByText(/House House/)).not.toBeInTheDocument();
});
