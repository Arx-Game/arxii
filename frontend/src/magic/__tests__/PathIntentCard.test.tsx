/**
 * PathIntentCard component tests.
 *
 * Verifies: renders intent name + clear button when intent is set;
 * renders nothing when intent is null; clear button calls useClearPathIntent
 * mutation with the characterId.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { PathIntentCard } from '../components/PathIntentCard';
import type { PathIntentResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock api so hooks resolve without network.
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getPathIntent: vi.fn(),
  deletePathIntent: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INTENT_PRESENT: PathIntentResponse = {
  intent: {
    id: 10,
    declared_at: '2026-06-01T00:00:00Z',
    intended_path: {
      id: 3,
      name: 'Path of Embers',
      stage: 2,
      stage_display: 'Kindled',
      description: 'A smoldering path.',
    },
  },
};

const INTENT_NULL: PathIntentResponse = { intent: null };

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PathIntentCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders intent name and stage_display when intent is set', async () => {
    vi.mocked(api.getPathIntent).mockResolvedValue(INTENT_PRESENT);

    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });

    const card = await screen.findByTestId('path-intent-card');
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent('Path of Embers');
    expect(card).toHaveTextContent('Kindled');
  });

  it('renders nothing when intent is null', async () => {
    vi.mocked(api.getPathIntent).mockResolvedValue(INTENT_NULL);

    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });

    // Wait for the query to fire.
    await vi.waitFor(() => expect(api.getPathIntent).toHaveBeenCalled());

    expect(screen.queryByTestId('path-intent-card')).not.toBeInTheDocument();
  });

  it('clear button calls deletePathIntent with the characterId', async () => {
    vi.mocked(api.getPathIntent).mockResolvedValue(INTENT_PRESENT);
    vi.mocked(api.deletePathIntent).mockResolvedValue(undefined);

    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });

    const clearBtn = await screen.findByTestId('path-intent-clear');
    fireEvent.click(clearBtn);

    await vi.waitFor(() => expect(api.deletePathIntent).toHaveBeenCalledWith(42));
  });
});
