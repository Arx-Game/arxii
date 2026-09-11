/**
 * XpLedgerCard tests (#3748). Mocks `@/progression/queries` — the sibling
 * advancement cards' idiom (no msw).
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { XpLedgerCard } from './XpLedgerCard';
import type { CharacterXpLedger } from '@/progression/types';

vi.mock('@/progression/queries', () => ({
  useCharacterXpLedgerQuery: vi.fn(),
}));

import * as progressionQueries from '@/progression/queries';

type LedgerQueryResult = ReturnType<typeof progressionQueries.useCharacterXpLedgerQuery>;

function mockLedger(data: CharacterXpLedger | undefined, error: Error | null = null) {
  vi.mocked(progressionQueries.useCharacterXpLedgerQuery).mockReturnValue({
    data,
    isLoading: false,
    error,
  } as unknown as LedgerQueryResult);
}

it('shows what was earned on and spent on the character', () => {
  mockLedger({ earned: 1240, spent: 900, locked: 0 });

  renderWithProviders(<XpLedgerCard sheetId={7} />);

  expect(screen.getByText('1,240 XP')).toBeInTheDocument();
  expect(screen.getByText('900 XP')).toBeInTheDocument();
});

it('shows spent above earned without complaint — the account pool is the balance', () => {
  // A second character funded out of XP the first one earned: normal, not an error.
  mockLedger({ earned: 50, spent: 800, locked: 0 });

  renderWithProviders(<XpLedgerCard sheetId={7} />);

  expect(screen.getByText('800 XP')).toBeInTheDocument();
  expect(screen.getByText('50 XP')).toBeInTheDocument();
});

it('shows the creation-locked pool only when there is one', () => {
  mockLedger({ earned: 100, spent: 0, locked: 0 });
  const { unmount } = renderWithProviders(<XpLedgerCard sheetId={7} />);
  expect(screen.queryByText('Locked from creation')).not.toBeInTheDocument();
  unmount();

  mockLedger({ earned: 100, spent: 0, locked: 60 });
  renderWithProviders(<XpLedgerCard sheetId={7} />);
  expect(screen.getByText('Locked from creation')).toBeInTheDocument();
  expect(screen.getByText('60 XP')).toBeInTheDocument();
});

it('surfaces a failed load instead of rendering zeroes', () => {
  mockLedger(undefined, new Error('boom'));

  renderWithProviders(<XpLedgerCard sheetId={7} />);

  expect(screen.getByText('Failed to load the XP ledger.')).toBeInTheDocument();
  expect(screen.queryByText('Earned on')).not.toBeInTheDocument();
});
