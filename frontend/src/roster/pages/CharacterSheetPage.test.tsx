import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CharacterSheetPage } from './CharacterSheetPage';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RosterEntryData } from '../types';

vi.mock('../queries', () => ({
  useRosterEntryQuery: vi.fn(),
  useMyRosterEntriesQuery: vi.fn(),
}));
import { useRosterEntryQuery, useMyRosterEntriesQuery } from '../queries';

const mockUseRosterEntryQuery = vi.mocked(useRosterEntryQuery);
const mockUseMyRosterEntriesQuery = vi.mocked(useMyRosterEntriesQuery);

describe('CharacterSheetPage', () => {
  beforeEach(() => {
    // Default: user has no characters — so MessagesSection is hidden.
    mockUseMyRosterEntriesQuery.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof useMyRosterEntriesQuery>);
  });

  it('shows loading state', () => {
    mockUseRosterEntryQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      isPending: true,
      isSuccess: false,
    } as unknown as UseQueryResult<RosterEntryData, Error>);
    renderWithProviders(
      <Routes>
        <Route path="/:id" element={<CharacterSheetPage />} />
      </Routes>,
      { initialEntries: ['/1'] }
    );
    expect(screen.getByText(/Loading.../i)).toBeInTheDocument();
  });

  it('shows not found when no entry', () => {
    mockUseRosterEntryQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      isSuccess: true,
    } as unknown as UseQueryResult<RosterEntryData, Error>);
    renderWithProviders(
      <Routes>
        <Route path="/:id" element={<CharacterSheetPage />} />
      </Routes>,
      { initialEntries: ['/1'] }
    );
    expect(screen.getByText(/Character not found/i)).toBeInTheDocument();
  });
});
