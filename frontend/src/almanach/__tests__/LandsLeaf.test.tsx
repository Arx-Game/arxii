/**
 * LandsLeaf (#3983 Task 9) — opens folded (no barony page shown), then a
 * row's own disclosure button opens `BaronyPage` beneath the table.
 *
 * Fixture uses the real `AlmanachBarony` field names (`id`, not the
 * sketch's `domain_id`; `population: number`, never `null`).
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { LandsLeaf } from '../document/LandsLeaf';
import type { AlmanachDocumentLands } from '../types';

const lands: AlmanachDocumentLands = {
  count: 2,
  population: 0,
  produces: ['salt'],
  seat: 'Perdition',
  baronies: [
    {
      id: 3,
      name: 'Perdition',
      in: 'County of Inferna',
      hall: 'the Palazzo Ardente',
      is_seat: true,
      description: 'Palazzos.',
      land_shapes: ['Coast'],
      population: 0,
    },
    {
      id: 4,
      name: 'Seawatch',
      in: 'Ardor',
      hall: '',
      is_seat: false,
      description: '',
      land_shapes: [],
      population: 0,
    },
  ],
};

test('opens folded and expands a barony to its page', async () => {
  renderWithProviders(<LandsLeaf houseName="Piropa" lands={lands} onDescribe={() => {}} />);
  expect(screen.getByRole('heading', { name: /lands of piropa/i })).toBeInTheDocument();
  expect(screen.queryByDisplayValue('Palazzos.')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /expand perdition/i }));
  expect(screen.getByDisplayValue('Palazzos.')).toBeInTheDocument();
  expect(screen.getByText('Undefined')).toBeInTheDocument();
});
