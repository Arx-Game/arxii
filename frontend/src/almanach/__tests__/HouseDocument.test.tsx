/**
 * HouseDocument (#3983 Task 9) — smoke test: it opens on The House with the
 * contents rail (House/Family, Realm/Lands/Estate) and the record rail
 * around it, and the particle-example gloss carries the house's real value.
 *
 * The `doc` fixture is shaped after the REAL wire types (`HouseDocument`,
 * `types.ts`) — `default_succession_law` (not the sketch's `succession`),
 * `estate: []` (a list, never `null` — `_estate_payload` always returns a
 * list), `lands.baronies[].id` (not `domain_id`).
 */
import { screen } from '@testing-library/react';
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
  realm: { sworn_to: '', obligation_pct: null, holds: 'Inferna', demesne: [], vassals: [] },
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
