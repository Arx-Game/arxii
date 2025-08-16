import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CharacterSheetPage } from './CharacterSheetPage';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RosterEntryData } from '../types';

vi.mock('../queries', () => ({
  useRosterEntryQuery: vi.fn(),
}));
import { useRosterEntryQuery } from '../queries';

const mockUseRosterEntryQuery = vi.mocked(useRosterEntryQuery);

describe('CharacterSheetPage', () => {
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
