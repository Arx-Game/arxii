import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AlmanachPage } from '../AlmanachPage';
import type { LadderRow } from '../types';

// Perdition is listed FIRST so it — not Fervor — is the savebar's default
// "under" context (`tree[0]`, `AlmanachPage.tsx`); selecting Fervor below
// then proves the click actually changes the dialog's parent, not just
// that the default happens to match.
const rows = [
  {
    title_id: 3,
    name: 'Perdition',
    is_defined: true,
    tier: 'barony',
    level: 46,
    parent_title_id: null,
    house_id: 9,
    house_name: 'Piropa',
    state: 'Held',
    is_seat_of: 'Piropa',
    sworn_to: 'County of Inferna',
    demesne: 1,
    vassals: 0,
    claimable: false,
    seat_domain_id: null,
    comes_with: '',
  },
  {
    title_id: 1,
    name: 'Fervor',
    is_defined: true,
    tier: 'duchy',
    level: 56,
    parent_title_id: null,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 1,
    vassals: 2,
    claimable: true,
    seat_domain_id: null,
    comes_with: '',
  },
] satisfies LadderRow[];

vi.mock('../queries', () => ({
  useRealms: () => ({
    data: {
      results: [
        {
          id: 1,
          name: 'Inferna',
          formal_name: 'Grand Principality of Inferna',
          default_tithe_pct: 10,
          unclaimed_by_tier: {},
        },
      ],
    },
  }),
  useLadder: () => ({ data: { rows, unclaimed_by_tier: { duchy: 1, barony: 0 } } }),
  useHouses: () => ({ data: { results: [] } }),
  useAlmanachMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/staff/almanach/realms/:realmId" element={<AlmanachPage />} />
    </Routes>,
    { initialEntries: ['/staff/almanach/realms/1'] }
  );
}

test("selecting a rung sets the plant dialog's under field to that rung, not the default root", async () => {
  renderPage();

  // With nothing selected, the savebar defaults to the first root (Perdition).
  await userEvent.click(screen.getByRole('button', { name: /plant a rung/i }));
  expect(within(screen.getByRole('dialog')).getByText('Perdition')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  // Selecting Fervor's own name/title button changes that default.
  await userEvent.click(screen.getByRole('button', { name: 'Select Fervor' }));
  await userEvent.click(screen.getByRole('button', { name: /plant a rung/i }));

  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('Fervor')).toBeInTheDocument();
  expect(within(dialog).getByText('duchy')).toBeInTheDocument();
  expect(within(dialog).queryByText('Perdition')).not.toBeInTheDocument();
});
