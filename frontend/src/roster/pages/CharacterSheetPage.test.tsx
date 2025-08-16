import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '../../test/utils/renderWithProviders';
import { CharacterSheetPage } from './CharacterSheetPage';

vi.mock('../queries', () => ({
  useRosterEntryQuery: vi.fn(),
}));
import { useRosterEntryQuery } from '../queries';

const mockUseRosterEntryQuery = vi.mocked(useRosterEntryQuery);

describe('CharacterSheetPage', () => {
  it('shows loading state', () => {
    mockUseRosterEntryQuery.mockReturnValue({ data: null, isLoading: true });
    renderWithProviders(
      <Routes>
        <Route path="/:id" element={<CharacterSheetPage />} />
      </Routes>,
      { initialEntries: ['/1'] }
    );
    expect(screen.getByText(/Loading.../i)).toBeInTheDocument();
  });

  it('shows not found when no entry', () => {
    mockUseRosterEntryQuery.mockReturnValue({ data: null, isLoading: false });
    renderWithProviders(
      <Routes>
        <Route path="/:id" element={<CharacterSheetPage />} />
      </Routes>,
      { initialEntries: ['/1'] }
    );
    expect(screen.getByText(/Character not found/i)).toBeInTheDocument();
  });
});
