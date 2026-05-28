/**
 * MissionBrowserPage smoke tests.
 *
 * Verifies the + New Mission button is present and navigates to
 * /staff/missions/new on click.
 *
 * MissionDetailPanel is mocked out to keep the test surface minimal —
 * its own hooks fire separate queries that are not the subject here.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { MissionBrowserPage } from '../pages/MissionBrowserPage';
import * as queries from '../queries';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Avoid rendering the full MissionDetailPanel — it calls useMissionTemplate
// and useMissionCategories, which are not the focus of this test.
vi.mock('../components/MissionDetailPanel', () => ({
  MissionDetailPanel: () => <div data-testid="mission-detail-panel-stub" />,
}));

describe('MissionBrowserPage', () => {
  it('renders + New Mission button and navigates on click', () => {
    vi.spyOn(queries, 'useMissionTemplates').mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useMissionTemplates>);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <MissionBrowserPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const btn = screen.getByRole('button', { name: /new mission/i });
    fireEvent.click(btn);
    expect(mockNavigate).toHaveBeenCalledWith('/staff/missions/new');
  });
});
