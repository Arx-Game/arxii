/**
 * Error-card render tests for MissionCanvasPage.
 *
 * The page parses the URL :id param with a Number.isFinite guard and shows
 * an explicit error card for invalid (non-numeric) ids. These tests assert:
 *   - isError from the query → the "Couldn't load" error card renders
 *   - non-numeric :id → the "Missing or invalid id" error card renders
 *
 * Per #686, GiverEditorPage was removed; coverage for that page dropped
 * with it.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';

import * as queries from '../queries';

function withProviders(initialPath: string, routePattern: string) {
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

// ---------------------------------------------------------------------------
// MissionCanvasPage
// ---------------------------------------------------------------------------

// Import AFTER vi.mock calls below.
import { MissionCanvasPage } from '../pages/MissionCanvasPage';

describe('MissionCanvasPage error cards', () => {
  it('renders isError card when the query errors on a valid id', () => {
    vi.spyOn(queries, 'useMissionTemplate').mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof queries.useMissionTemplate>);

    render(<MissionCanvasPage />, {
      wrapper: withProviders('/staff/missions/42/canvas', '/staff/missions/:id/canvas'),
    });

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toMatch(/couldn't load this mission/i);
  });

  it('renders invalid-id card for a non-numeric :id param', () => {
    // When id is undefined the query hook is not even called (enabled: false),
    // but we still need useMissionTemplate in scope; provide a neutral mock.
    vi.spyOn(queries, 'useMissionTemplate').mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof queries.useMissionTemplate>);

    render(<MissionCanvasPage />, {
      wrapper: withProviders('/staff/missions/abc/canvas', '/staff/missions/:id/canvas'),
    });

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toMatch(/missing or invalid id in url/i);
  });
});
