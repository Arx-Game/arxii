import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { NearXPLockProspect, Thread } from '../../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useCrossXPLock: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { XPLockBoundaryPanel } from '../XPLockBoundaryPanel';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const makeThread = (overrides: Partial<Thread> = {}): Thread => ({
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'TRAIT',
  name: 'Test Thread',
  description: '',
  level: 10,
  developed_points: 20,
  path_cap: 30,
  anchor_cap: 30,
  effective_cap: 30,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  ...overrides,
});

const makeProspect = (overrides: Partial<NearXPLockProspect> = {}): NearXPLockProspect => ({
  thread_id: 1,
  boundary_level: 20,
  xp_cost: 10,
  dev_points_to_boundary: 5,
  ...overrides,
});

type MutationState = {
  mutate: ReturnType<typeof vi.fn>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
};

function makeMutation(overrides: Partial<MutationState> = {}): MutationState {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(magicQueries.useCrossXPLock).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.useCrossXPLock>
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('XPLockBoundaryPanel', () => {
  it('renders nothing when prospect is null', () => {
    const { container } = render(
      <XPLockBoundaryPanel thread={makeThread()} prospect={null} accountAvailableXP={100} />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when thread level is already at or past boundary', () => {
    const { container } = render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 20 })}
        prospect={makeProspect({ boundary_level: 20 })}
        accountAvailableXP={100}
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders panel when thread level is below boundary', () => {
    render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 10 })}
        prospect={makeProspect({ boundary_level: 20, xp_cost: 10 })}
        accountAvailableXP={100}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('xp-lock-boundary-panel')).toBeInTheDocument();
    expect(screen.getByTestId('xp-lock-description')).toBeInTheDocument();
  });

  it('shows correct boundary level and xp cost', () => {
    render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 10 })}
        prospect={makeProspect({ boundary_level: 20, xp_cost: 15 })}
        accountAvailableXP={20}
      />,
      { wrapper: createWrapper() }
    );
    // boundary_level 20 displayed as 20/10 = 2
    expect(screen.getByTestId('xp-lock-description').textContent).toContain('2');
    expect(screen.getByTestId('xp-lock-description').textContent).toContain('15');
    // available XP
    expect(screen.getByTestId('xp-available').textContent).toBe('20');
  });

  it('disables button when accountAvailableXP < xp_cost', () => {
    render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 10 })}
        prospect={makeProspect({ boundary_level: 20, xp_cost: 50 })}
        accountAvailableXP={30}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('xp-lock-pay-button')).toBeDisabled();
  });

  it('enables button when accountAvailableXP >= xp_cost', () => {
    render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 10 })}
        prospect={makeProspect({ boundary_level: 20, xp_cost: 10 })}
        accountAvailableXP={10}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('xp-lock-pay-button')).toBeEnabled();
  });

  it('calls mutate with correct args when Pay XP button is clicked', () => {
    const mockMutate = vi.fn();
    vi.mocked(magicQueries.useCrossXPLock).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.useCrossXPLock
      >
    );

    render(
      <XPLockBoundaryPanel
        thread={makeThread({ id: 5, level: 10 })}
        prospect={makeProspect({ thread_id: 5, boundary_level: 20, xp_cost: 10 })}
        accountAvailableXP={50}
      />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByTestId('xp-lock-pay-button'));

    expect(mockMutate).toHaveBeenCalledOnce();
    expect(mockMutate).toHaveBeenCalledWith({
      threadId: 5,
      body: { boundary_level: 20 },
    });
  });

  it('shows error message inline when mutation fails', () => {
    vi.mocked(magicQueries.useCrossXPLock).mockReturnValue(
      makeMutation({
        isError: true,
        error: new Error('Insufficient XP'),
      }) as unknown as ReturnType<typeof magicQueries.useCrossXPLock>
    );

    render(
      <XPLockBoundaryPanel
        thread={makeThread({ level: 10 })}
        prospect={makeProspect({ boundary_level: 20, xp_cost: 5 })}
        accountAvailableXP={100}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('xp-lock-error')).toBeInTheDocument();
    expect(screen.getByText('Insufficient XP')).toBeInTheDocument();
  });
});
