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
vi.mock('@/orgs/queries', () => ({
  useOrganizationByName: vi.fn(),
}));
vi.mock('@/vitals/components/VitalsPanel', () => ({
  VitalsPanel: vi.fn(() => <div data-testid="vitals-panel-mock" />),
}));
import { useRosterEntryQuery, useMyRosterEntriesQuery } from '../queries';
import { useOrganizationByName } from '@/orgs/queries';

const mockUseRosterEntryQuery = vi.mocked(useRosterEntryQuery);
const mockUseMyRosterEntriesQuery = vi.mocked(useMyRosterEntriesQuery);
const mockUseOrganizationByName = vi.mocked(useOrganizationByName);

describe('CharacterSheetPage', () => {
  beforeEach(() => {
    // Default: user has no characters — so MessagesSection is hidden.
    mockUseMyRosterEntriesQuery.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof useMyRosterEntriesQuery>);
    // Default: no same-named org resolved — family renders as plain text.
    mockUseOrganizationByName.mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof useOrganizationByName>);
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

  it('renders the vitals panel for a loaded entry', () => {
    const entry: RosterEntryData = {
      id: 1,
      character: {
        id: 42,
        name: 'Test Character',
        galleries: [],
      },
      profile_picture: null,
      tenures: [],
      can_apply: false,
      fullname: 'Test Character',
      quote: '',
      description: '',
      creation_provenance: 'player',
      creation_provenance_display: 'Player-created',
      created_for_table_name: null,
    };
    mockUseRosterEntryQuery.mockReturnValue({
      data: entry,
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
    expect(screen.getByTestId('vitals-panel-mock')).toBeInTheDocument();
  });

  it('renders a covenant link and role under the name when covenant is set', () => {
    const entry: RosterEntryData = {
      id: 1,
      character: {
        id: 42,
        name: 'Test Character',
        galleries: [],
        covenant: { id: 7, name: 'Covenant of the Dawn', role: 'Vanguard' },
      },
      profile_picture: null,
      tenures: [],
      can_apply: false,
      fullname: 'Test Character',
      quote: '',
      description: '',
      creation_provenance: 'player',
      creation_provenance_display: 'Player-created',
      created_for_table_name: null,
    };
    mockUseRosterEntryQuery.mockReturnValue({
      data: entry,
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
    const link = screen.getByRole('link', { name: /Covenant of the Dawn/i });
    expect(link).toHaveAttribute('href', '/covenants/7');
    expect(screen.getByText(/Vanguard/i)).toBeInTheDocument();
  });

  it('omits the covenant line when covenant is null', () => {
    const entry: RosterEntryData = {
      id: 1,
      character: {
        id: 42,
        name: 'Test Character',
        galleries: [],
        covenant: null,
      },
      profile_picture: null,
      tenures: [],
      can_apply: false,
      fullname: 'Test Character',
      quote: '',
      description: '',
      creation_provenance: 'player',
      creation_provenance_display: 'Player-created',
      created_for_table_name: null,
    };
    mockUseRosterEntryQuery.mockReturnValue({
      data: entry,
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
    expect(screen.queryByRole('link', { name: /Covenant of the Dawn/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Vanguard/i)).not.toBeInTheDocument();
  });
});
