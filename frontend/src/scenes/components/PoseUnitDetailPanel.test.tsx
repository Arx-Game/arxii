/**
 * Tests for PoseUnitDetailPanel — expand/collapse with lazy fetch.
 * Phase 9, Task 9.4.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import type { ReactNode } from 'react';
import { PoseUnitDetailPanel } from './PoseUnitDetailPanel';
import { deepLinkModalSlice } from '@/store/deepLinkModalSlice';

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

function makeStore() {
  return configureStore({ reducer: { deepLinkModal: deepLinkModalSlice.reducer } });
}

function Wrapper({
  children,
  store = makeStore(),
}: {
  children: ReactNode;
  store?: ReturnType<typeof makeStore>;
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <Provider store={store}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </Provider>
  );
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
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[1, 2]} />
      </Wrapper>
    );

    expect(screen.getByText(/Loading outcome details/i)).toBeInTheDocument();
  });

  it('shows empty message when effects list is empty (v1 behavior)', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [{ action_interaction_id: 1, effects: [] }],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

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
    } as unknown as ReturnType<typeof useOutcomeDetails>);

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

  it('shows error message when hook returns isError', () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[1]} />
      </Wrapper>
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load outcome details.');
  });

  it('calls useOutcomeDetails with the provided IDs', () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[10, 20, 30]} />
      </Wrapper>
    );

    expect(mockUseOutcomeDetails).toHaveBeenCalledWith([10, 20, 30]);
  });

  it('dispatches openDeepLink with the target when a deep-link effect is clicked', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        {
          action_interaction_id: 5,
          effects: [
            {
              kind: 'condition',
              label: 'Bleeding applied',
              deep_link: { modal: 'condition', id: 7 },
            },
            { kind: 'status', label: 'Stunned', deep_link: null },
          ],
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    const store = makeStore();
    const user = userEvent.setup();
    render(
      <Wrapper store={store}>
        <PoseUnitDetailPanel actionInteractionIds={[5]} />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /Bleeding applied/i }));

    expect(store.getState().deepLinkModal.current).toEqual({ modal: 'condition', id: 7 });
  });

  it('renders the PowerLedgerPanel when an outcome carries a power_ledger', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        {
          action_interaction_id: 5,
          effects: [{ kind: 'damage', label: 'Knight took 6 damage', deep_link: null }],
          power_ledger: {
            entries: [
              {
                stage: 'base',
                source_label: 'Channeled',
                op: 'add',
                amount: 10,
                running_total: 10,
              },
            ],
            total: 10,
          },
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[5]} />
      </Wrapper>
    );

    await waitFor(() => {
      expect(screen.getByTestId('power-ledger-panel')).toBeInTheDocument();
    });
  });

  it('does not render the PowerLedgerPanel when no power_ledger is present', async () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        {
          action_interaction_id: 5,
          effects: [{ kind: 'damage', label: 'Knight took 6 damage', deep_link: null }],
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[5]} />
      </Wrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('Knight took 6 damage')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('power-ledger-panel')).toBeNull();
  });

  it('renders a non-deep-linked effect as plain text, not a button', () => {
    mockUseOutcomeDetails.mockReturnValue({
      data: [
        {
          action_interaction_id: 5,
          effects: [
            {
              kind: 'condition',
              label: 'Bleeding applied',
              deep_link: { modal: 'condition', id: 7 },
            },
            { kind: 'status', label: 'Stunned', deep_link: null },
          ],
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useOutcomeDetails>);

    render(
      <Wrapper>
        <PoseUnitDetailPanel actionInteractionIds={[5]} />
      </Wrapper>
    );

    const plainRow = screen.getByText('Stunned').closest('div');
    expect(plainRow).not.toBeNull();
    expect(within(plainRow as HTMLElement).queryByRole('button')).toBeNull();
  });
});
