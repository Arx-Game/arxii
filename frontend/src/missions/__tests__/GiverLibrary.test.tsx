/**
 * GiverLibraryPage + GiverEditorPage rendering + dirty-state tests.
 *
 * Mocks the queries module so the components render against fixed
 * data. Verifies the list renders rows, the editor surfaces giver
 * fields, and the Save button gates on dirty state.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';

import type { MissionGiver, MissionGiverOffering } from '../types';

// Stable fixtures shared across both page mounts.
const FAKE_GIVER: MissionGiver = {
  id: 7,
  name: 'Old Hag',
  giver_kind: 'npc',
  target: 42,
  org: null,
  is_active: true,
  is_publishable: true,
};

const FAKE_OFFERINGS: MissionGiverOffering[] = [
  {
    id: 100,
    giver: 7,
    template: 5,
    weight_override: null,
    requirements_override: {},
  },
];

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useMissionGivers: () => ({
      data: { count: 1, next: null, previous: null, results: [FAKE_GIVER] },
      isLoading: false,
    }),
    useMissionGiver: (id: number | undefined) => ({
      data: id === FAKE_GIVER.id ? FAKE_GIVER : undefined,
      isLoading: false,
    }),
    useGiverOfferings: () => ({
      data: { count: 1, next: null, previous: null, results: FAKE_OFFERINGS },
      isLoading: false,
    }),
    useMissionTemplates: () => ({ data: { count: 0, next: null, previous: null, results: [] } }),
    usePredicateLeaves: () => ({ data: [], isLoading: false }),
    usePatchMissionGiver: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useDeleteMissionGiver: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useCreateMissionGiver: () => ({
      mutateAsync: vi.fn().mockResolvedValue(FAKE_GIVER),
      reset: vi.fn(),
      isPending: false,
      error: null,
    }),
    useCreateGiverOffering: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    }),
    usePatchGiverOffering: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useDeleteGiverOffering: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

import { GiverEditorPage } from '../pages/GiverEditorPage';
import { GiverLibraryPage } from '../pages/GiverLibraryPage';

function withProviders(initial: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/staff/missions/givers" element={children} />
          <Route path="/staff/missions/givers/:id" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('GiverLibraryPage', () => {
  it('renders giver rows and the new-giver toggle', () => {
    render(<GiverLibraryPage />, {
      wrapper: withProviders('/staff/missions/givers'),
    });
    expect(screen.getByTestId('giver-list')).toBeInTheDocument();
    expect(screen.getByText('Old Hag')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new giver/i })).toBeInTheDocument();
  });

  it('opens the create form when "+ New giver" is clicked', async () => {
    const user = userEvent.setup();
    render(<GiverLibraryPage />, {
      wrapper: withProviders('/staff/missions/givers'),
    });
    await user.click(screen.getByRole('button', { name: /new giver/i }));
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.queryByLabelText('Slug')).not.toBeInTheDocument();
  });
});

describe('GiverEditorPage', () => {
  it('renders giver fields populated from data', () => {
    render(<GiverEditorPage />, {
      wrapper: withProviders('/staff/missions/givers/7'),
    });
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Old Hag');
    expect(screen.getByText('Mission offerings')).toBeInTheDocument();
    // One offering row in the fixture.
    expect(screen.getAllByTestId('offering-row')).toHaveLength(1);
  });

  it('disables Save until a field is changed', async () => {
    const user = userEvent.setup();
    render(<GiverEditorPage />, {
      wrapper: withProviders('/staff/missions/givers/7'),
    });
    // Disambiguate from "Save" on each offering row via the giver-card Save:
    // the first Save in document order is the giver one.
    const saveButtons = screen.getAllByRole('button', { name: 'Save' });
    expect(saveButtons[0]).toBeDisabled();
    await user.clear(screen.getByLabelText('Name'));
    await user.type(screen.getByLabelText('Name'), 'New Name');
    const saveButtonsAfter = screen.getAllByRole('button', { name: 'Save' });
    expect(saveButtonsAfter[0]).toBeEnabled();
  });
});
