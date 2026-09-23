import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AlmanachPage } from '../AlmanachPage';
import type { LadderRow, RealmCharter } from '../types';

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
    chain_top_id: 3,
    claimant_name: '',
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
    chain_top_id: 1,
    claimant_name: '',
  },
] satisfies LadderRow[];

// Mutable indirection (mirrors `SeatPicker.test.tsx`'s own pattern) so
// `useLadder`/`useCharter`'s mocked data can vary per test — an empty
// ladder for the I9 root-plant tests, a populated charter for the
// deferred-item-1 Charter section test — without a second mock factory.
let mockRows: LadderRow[] = rows;
let mockCharter: RealmCharter | undefined;

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
  useLadder: () => ({ data: { rows: mockRows, unclaimed_by_tier: { duchy: 1, barony: 0 } } }),
  useHouses: () => ({ data: { results: [] } }),
  useCharter: () => ({ data: mockCharter }),
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

test('plant a rung is enabled and opens straight into root mode when the ladder is empty (I9)', async () => {
  mockRows = [];
  try {
    renderPage();
    const plantButton = screen.getByRole('button', { name: /plant a rung/i });
    expect(plantButton).not.toBeDisabled();
    await userEvent.click(plantButton);

    const dialog = screen.getByRole('dialog');
    // No parent to toggle away from — the root/nested seg never renders,
    // and the tier choices are the root set (empire/kingdom/duchy), never
    // county/barony (nothing exists yet to nest a county/barony under).
    expect(within(dialog).queryByRole('button', { name: /at the realm root/i })).toBeNull();
    expect(within(dialog).getByText('the realm')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'duchy' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'county' })).toBeNull();
  } finally {
    mockRows = rows;
  }
});

test(`plant a rung offers a root option when the level bar sits on the ladder's own top tier (I9)`, async () => {
  renderPage();
  // Nothing explicitly selected — the pressed tier defaults to 'duchy',
  // the ladder's own shallowest tier, so root-planting is offered
  // alongside the usual "under Perdition" default.
  await userEvent.click(screen.getByRole('button', { name: /plant a rung/i }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('Perdition')).toBeInTheDocument();

  await userEvent.click(within(dialog).getByRole('button', { name: /at the realm root/i }));
  expect(within(dialog).getByText('the realm')).toBeInTheDocument();
  expect(within(dialog).getByRole('button', { name: 'kingdom' })).toBeInTheDocument();
});

test('the record rail renders the Charter section from useCharter', () => {
  mockCharter = {
    succession_law: { name: 'Infernal Enatic', codex_entry_id: 7 },
    particle: { born: 'aza', taken_in: 'azas' },
    quiddity_prompt: 'What does this house tend to?',
    capital_name: 'Arx City',
  };
  try {
    renderPage();
    // The contents rail's own inert "Charter" `<li>` also carries the word
    // "Charter" — scope to the record rail's own `<h4>` so the two don't
    // collide as duplicate text matches.
    expect(screen.getByRole('heading', { name: 'Charter', level: 4 })).toBeInTheDocument();
    expect(screen.getByText(/Infernal Enatic/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'codex' })).toHaveAttribute('href', '/codex/7');
    expect(screen.getByText('aza · azas')).toBeInTheDocument();
    expect(screen.getByText('What does this house tend to?')).toBeInTheDocument();
  } finally {
    mockCharter = undefined;
  }
});
