/**
 * Error-card render tests for NodePage and OptionPage.
 *
 * Both pages use local useQuery wrappers (useNode, useOption) that call
 * api.getMissionNode / api.getMissionOption directly. We mock the api
 * module to reject and let React Query settle into isError state, then
 * assert the inline error card renders instead of crashing to the global
 * ErrorBoundary.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the api module before importing pages that use it.
vi.mock('../api', () => ({
  getMissionNode: vi.fn(),
  getMissionOption: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionOptions: vi.fn(),
  listMissionRoutes: vi.fn(),
  listPredicateLeaves: vi.fn(),
  patchMissionNode: vi.fn(),
  patchMissionOption: vi.fn(),
}));

import * as api from '../api';
// Also mock useMissionTemplate so breadcrumb doesn't fire a real query.
import * as queries from '../queries';

import { NodePage } from '../pages/NodePage';
import { OptionPage } from '../pages/OptionPage';

function makeWrapper(initialPath: string, routePattern: string) {
  // retry: 0 so the query goes straight to error state without retrying.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path={routePattern} element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // useMissionTemplate called for the breadcrumb — keep it neutral.
  vi.spyOn(queries, 'useMissionTemplate').mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof queries.useMissionTemplate>);
  // listMissionOptions / listMissionRoutes used for the secondary lists.
  vi.mocked(api.listMissionOptions).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(api.listMissionRoutes).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(api.listPredicateLeaves).mockResolvedValue([]);
});

// ---------------------------------------------------------------------------
// NodePage
// ---------------------------------------------------------------------------

describe('NodePage error cards', () => {
  it('renders isError card when getMissionNode rejects', async () => {
    vi.mocked(api.getMissionNode).mockRejectedValue(new Error('network error'));

    render(<NodePage />, {
      wrapper: makeWrapper('/staff/missions/1/nodes/5', '/staff/missions/:id/nodes/:nodeId'),
    });

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert.textContent).toMatch(/couldn't load this node/i);
    });
  });
});

// ---------------------------------------------------------------------------
// OptionPage
// ---------------------------------------------------------------------------

describe('OptionPage error cards', () => {
  it('renders isError card when getMissionOption rejects', async () => {
    vi.mocked(api.getMissionOption).mockRejectedValue(new Error('network error'));

    render(<OptionPage />, {
      wrapper: makeWrapper(
        '/staff/missions/1/nodes/5/options/9',
        '/staff/missions/:id/nodes/:nodeId/options/:optionId'
      ),
    });

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert.textContent).toMatch(/couldn't load this option/i);
    });
  });
});
