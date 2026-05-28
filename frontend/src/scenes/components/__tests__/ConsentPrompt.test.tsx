import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { ConsentPrompt } from '../ConsentPrompt';
import type { ActionRequest } from '../../actionTypes';

vi.mock('../../actionQueries', () => ({
  fetchPendingRequests: vi.fn(),
  respondToRequest: vi.fn(),
}));

import { fetchPendingRequests } from '../../actionQueries';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function makeRequest(overrides: Partial<ActionRequest> = {}): ActionRequest {
  return {
    id: 1,
    initiator_persona: { id: 100, name: 'Mara' },
    action_name: 'Charm',
    technique_name: null,
    strain_commitment: 0,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('ConsentPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows strain text when strain_commitment > 0', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [makeRequest({ strain_commitment: 3 })],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Mara is committing 3 strain/i)).toBeInTheDocument();
    });
  });

  it('does NOT show strain text when strain_commitment === 0', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [makeRequest({ strain_commitment: 0 })],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    // Wait for the prompt to render
    await waitFor(() => {
      expect(screen.getByText(/wants to use/i)).toBeInTheDocument();
    });
    // Strain footnote must not appear
    expect(screen.queryByText(/is committing/i)).not.toBeInTheDocument();
  });
});
