/**
 * isError card tests for the list-style mission pages.
 *
 * `useMissionTemplates` and `useMissionGivers` (per queries.ts) deliberately
 * drop `throwOnError` so their consuming pages handle isError inline rather
 * than crashing to the global ErrorBoundary. This file pins that contract:
 * each list page renders its inline "couldn't load" card when the hook
 * returns isError: true.
 *
 * Closes #589 item 5 — companion to the PageErrorCards / DrillDownPageErrorCards
 * tests that cover the throwOnError'd detail pages.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { GiverLibraryPage } from '../pages/GiverLibraryPage';
import { MissionBrowserPage } from '../pages/MissionBrowserPage';
import * as queries from '../queries';

// MissionDetailPanel fires its own queries; stub it so this file's mocks stay
// minimal. Mirrors the pattern from MissionBrowserPage.test.tsx.
vi.mock('../components/MissionDetailPanel', () => ({
  MissionDetailPanel: () => <div data-testid="mission-detail-panel-stub" />,
}));

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MissionBrowserPage isError card', () => {
  it('renders the inline "Couldn\'t load missions" card when useMissionTemplates errors', () => {
    vi.spyOn(queries, 'useMissionTemplates').mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useMissionTemplates>);

    render(withProviders(<MissionBrowserPage />));

    const errorCard = screen.getByTestId('mission-list-error');
    expect(errorCard).toBeInTheDocument();
    expect(errorCard).toHaveAttribute('role', 'alert');
    expect(errorCard).toHaveTextContent(/couldn't load missions/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});

describe('GiverLibraryPage isError card', () => {
  it('renders the inline "Couldn\'t load givers" card when useMissionGivers errors', () => {
    vi.spyOn(queries, 'useMissionGivers').mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useMissionGivers>);

    render(withProviders(<GiverLibraryPage />));

    const errorCard = screen.getByTestId('giver-list-error');
    expect(errorCard).toBeInTheDocument();
    expect(errorCard).toHaveAttribute('role', 'alert');
    expect(errorCard).toHaveTextContent(/couldn't load givers/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
