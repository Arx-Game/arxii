/**
 * Tests for PoseUnitDetailPanel — expand/collapse with lazy fetch.
 * Phase 9, Task 9.4.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { PoseUnitDetailPanel } from './PoseUnitDetailPanel';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn(),
}));

import { useOutcomeDetails } from '@/combat/queries';

const mockUseOutcomeDetails = vi.mocked(useOutcomeDetails);

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PoseUnitDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state while fetching', () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[1, 2]} />
      </Wrapper>
    );

    expect(screen.getByText(/Loading outcome details/i)).toBeInTheDocument();
  });

  it('shows empty message when effects list is empty (v1 behavior)', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        { action_interaction_id: 1, effects: [] },
      ],
      isLoading: false,
    } as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[1]} />
      </Wrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('No recorded effects.')).toBeInTheDocument();
    });
  });

  it('renders effects when data is available', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        {
          action_interaction_id: 5,
          effects: [
            { kind: 'damage', label: 'Aerande took 4 damage', deep_link: null },
            {
              kind: 'condition',
              label: 'Burning x2 applied to Knight',
              deep_link: { modal: 'condition', id: 7 },
            },
          ],
        },
      ],
      isLoading: false,
    } as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[5]} />
      </Wrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('Aerande took 4 damage')).toBeInTheDocument();
      expect(screen.getByText('Burning x2 applied to Knight')).toBeInTheDocument();
    });
  });

  it('calls useOutcomeDetails with the provided IDs', () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [],
      isLoading: false,
    } as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[10, 20, 30]} />
      </Wrapper>
    );

    expect(mockUseOutcomeDetails).toHaveBeenCalledWith([10, 20, 30]);
  });
});
