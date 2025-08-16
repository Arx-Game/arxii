import { screen } from '@testing-library/react';
import { RosterListPage } from './RosterListPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { vi } from 'vitest';

// Mock the queries
vi.mock('../queries', () => ({
  useRostersQuery: () => ({
    data: [{ id: 1, name: 'Test Roster' }],
    isLoading: false,
  }),
  useRosterEntriesQuery: () => ({
    data: {
      results: [],
      previous: null,
      next: null,
    },
    isLoading: false,
  }),
}));

describe('RosterListPage', () => {
  it('should render gender filter select without throwing errors', () => {
    // This test verifies that the component renders without the Select.Item empty value error
    // The error would occur during rendering, not during user interaction
    renderWithProviders(<RosterListPage />);

    // If we got this far without throwing, the fix worked
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('should not throw error after fixing empty string value', () => {
    // This should not throw any errors now that we use '__any__' instead of empty string
    expect(() => {
      renderWithProviders(<RosterListPage />);
    }).not.toThrow();
  });
});
