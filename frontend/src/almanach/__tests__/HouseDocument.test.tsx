/**
 * HouseDocument (#3983 Task 9) — smoke test: it opens on The House with the
 * contents rail (House/Family, Realm/Lands/Estate) and the record rail
 * around it, and the particle-example gloss carries the house's real value.
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
    particle_example: 'Océane aza Piropa · Raffaele azas Piropa',
    default_succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: null },
    aspects: [],
    features: [],
    offices: [],
  },
  family: { nodes: [], parentage: [], unions: [] },
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
};

test('opens on The House with the contents rail and the record rail', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  expect(screen.getByRole('heading', { name: /house piropa/i })).toBeInTheDocument();
  expect(screen.getByText('The Family')).toBeInTheDocument();
  expect(screen.getByText('Lands')).toBeInTheDocument();
  expect(screen.getByText('Océane aza Piropa · Raffaele azas Piropa')).toBeInTheDocument();
  // The record rail (aside.record) opens alongside The House.
  expect(screen.getByText('on record')).toBeInTheDocument();
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
  const gentry = screen.getByRole('button', { name: 'Gentry' });
  expect(gentry).not.toBeDisabled();
  await userEvent.click(gentry);
  expect(gentry).toHaveAttribute('aria-pressed', 'true');

  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(mutate).toHaveBeenCalledWith({ org_id: 9, house_state: 'gentry' });
});

test('Gentry stays disabled ("Luxen only") when the realm theme is not luxen', () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  const gentry = screen.getByRole('button', { name: 'Gentry' });
  expect(gentry).toBeDisabled();
  expect(gentry).toHaveAttribute('title', 'Luxen only');
});

test("the ladder record door links to the realm's own ladder page when realm_id is set", async () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Realm' }));
  const door = screen.getByRole('link', { name: 'the ladder' });
  expect(door).toHaveAttribute('href', '/staff/almanach/realms/1');
});

test("the ladder record door renders a labeled dash when the house's realm carries no id", async () => {
  const noRealmIdDoc: HouseDocumentPayload = { ...doc, realm: { ...doc.realm, realm_id: null } };
  vi.mocked(queries.useHouseDocument).mockReturnValue({
    data: noRealmIdDoc,
    isLoading: false,
  } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Realm' }));
  expect(screen.queryByRole('link', { name: 'the ladder' })).not.toBeInTheDocument();
  expect(screen.getByText('the ladder')).toBeInTheDocument();
});

test('swearing a house prefills the tithe percent from the realm default', async () => {
  vi.mocked(queries.useHouseDocument).mockReturnValue({ data: doc, isLoading: false } as never);
  vi.mocked(queries.useAllHouses).mockReturnValue({ data: { results: [] } } as never);
  renderWithProviders(<HouseDocument houseId={9} />);
  await userEvent.click(screen.getByRole('button', { name: 'Realm' }));
  await userEvent.click(screen.getByRole('button', { name: 'swear a house' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByLabelText('tithe percent')).toHaveValue(10);
});
