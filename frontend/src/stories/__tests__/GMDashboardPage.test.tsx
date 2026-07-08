/**
 * GMDashboardPage Tests (#2004)
 *
 * Smoke tests: renders without crashing, shows the dashboard sections,
 * and renders the 403 not-a-GM error state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { GMDashboardPage } from '../pages/GMDashboardPage';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';

function withProviders(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const mockDashboard = {
  episodes_ready_to_run: [],
  pending_agm_claims: [],
  assigned_session_requests: [],
  waiting_for_gm: [],
  my_tables: [{ id: 1, name: 'Test Table', membership_count: 3 }],
  pending_story_offers: [],
  evidence_summary: {
    level: 'gm',
    stories_running: 2,
    beats_completed_by_risk: {},
    last_active_at: '2026-07-08T00:00:00Z',
  },
};

describe('GMDashboardPage', () => {
  it('renders dashboard sections on success', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText('GM Dashboard')).toBeInTheDocument();
    });
    expect(screen.getByText('Test Table')).toBeInTheDocument();
    expect(screen.getByText('gm')).toBeInTheDocument();
  });

  it('renders not-a-GM message on 403', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: false,
      status: 403,
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText(/You must be a GM/i)).toBeInTheDocument();
    });
  });
});
