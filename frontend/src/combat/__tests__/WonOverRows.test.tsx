/**
 * Tests for WonOverRows — the won-over opponents on the outcome rail (#4091).
 */

import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { store } from '@/store/store';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useDispatchPlayerAction } from '@/combat/queries';
import { createActionRequest } from '@/scenes/actionQueries';
import { useCompanionArchetypes } from '@/companions/queries';
import { useCharacterGifts } from '@/magic/queries';
import { WonOverRows } from '../components/WonOverRows';
import type { WonOverRow } from '../components/WonOverRows';

vi.mock('@/combat/queries', async () => {
  const actual = await vi.importActual<typeof import('@/combat/queries')>('@/combat/queries');
  return {
    ...actual,
    useDispatchPlayerAction: vi.fn(),
  };
});

vi.mock('@/scenes/actionQueries', async () => {
  const actual =
    await vi.importActual<typeof import('@/scenes/actionQueries')>('@/scenes/actionQueries');
  return {
    ...actual,
    createActionRequest: vi.fn(() => Promise.resolve({ status: 'resolved' })),
  };
});

vi.mock('@/companions/queries', () => ({
  useCompanionArchetypes: vi.fn(),
}));

vi.mock('@/magic/queries', () => ({
  useCharacterGifts: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mirrors the repo convention for testing a `@/components/ui/select` consumer
// (e.g. PlayerBoundaryFormDialog.test.tsx / AddDialog.test.tsx): a plain
// native <select> stand-in, label-associated via the surrounding <label> text
// in WonOverRows.tsx rather than any special aria-label plumbing.
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: ReactNode;
  }) => (
    <select value={value} onChange={(e) => onValueChange?.(e.target.value)}>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

const mockUseDispatchPlayerAction = vi.mocked(useDispatchPlayerAction);
const mockUseCompanionArchetypes = vi.mocked(useCompanionArchetypes);
const mockUseCharacterGifts = vi.mocked(useCharacterGifts);

function mockDispatch(mutate = vi.fn()) {
  mockUseDispatchPlayerAction.mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  return mutate;
}

/** Renders with the same providers as renderWithProviders, but also returns
 * the QueryClient instance so a test can spy on its invalidateQueries. */
function renderRowsWithClient(rows: WonOverRow[], characterId = 42, sceneId: string | null = '1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <WonOverRows rows={rows} characterId={characterId} sceneId={sceneId} />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
  return queryClient;
}

const baseRow: WonOverRow = {
  opponent_id: 7,
  name: 'Road Bandit',
  verb: 'charmed',
  source_label: "Wren's Sweet Talk",
  nameless: true,
  persona_id: null,
  present: true,
  condition: null,
  holds_until_settled: true,
  strength: 3,
  can_bind: true,
  can_take_into_service: false,
  can_send_away: true,
  can_settle: false,
};

describe('WonOverRows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch();
    mockUseCompanionArchetypes.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useCompanionArchetypes>);
    mockUseCharacterGifts.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useCharacterGifts>);
  });

  it('shows bind only when the viewer may bind', () => {
    renderWithProviders(<WonOverRows rows={[baseRow]} characterId={42} sceneId="1" />);

    expect(screen.getByText('Bind as companion')).toBeInTheDocument();
    // Nameless (ruling R2): never a Settle button, regardless of can_settle.
    expect(screen.queryByText('Settle')).not.toBeInTheDocument();
  });

  it('shows holds until settled for a rounds-measured hold', () => {
    renderWithProviders(
      <WonOverRows
        rows={[{ ...baseRow, holds_until_settled: true }]}
        characterId={42}
        sceneId="1"
      />
    );

    expect(screen.getByText(/holds until settled/)).toBeInTheDocument();
  });

  it('hides Bind for a row the viewer did not charm, and shows the charmer note', () => {
    renderWithProviders(
      <WonOverRows rows={[{ ...baseRow, can_bind: false }]} characterId={42} sceneId="1" />
    );

    expect(screen.queryByText('Bind as companion')).not.toBeInTheDocument();
    expect(screen.getByTestId('won-over-charmer-note-7')).toHaveTextContent(
      'only Wren can bind it'
    );
  });

  it('Send away dispatches send_away with the opponent id and invalidates the combat cache', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onSuccess({ backend: 'registry', deferred: false, success: true, message: 'Sent.' });
    });
    mockDispatch(mutate);

    const queryClient = renderRowsWithClient([{ ...baseRow, can_send_away: true }]);
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    await user.click(screen.getByText('Send away'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'send_away' },
          kwargs: { combat_opponent_id: 7 },
        },
        expect.any(Object)
      );
      expect(invalidateSpy).toHaveBeenCalled();
    });
  });

  it('shows a failure toast instead of swallowing an HTTP-level send_away error', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onError(new Error('Failed to dispatch action'));
    });
    mockDispatch(mutate);

    renderWithProviders(
      <WonOverRows rows={[{ ...baseRow, can_send_away: true }]} characterId={42} sceneId="1" />
    );

    await user.click(screen.getByText('Send away'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to dispatch action');
    });
  });

  it('Settle posts a settle action request for a persona-backed row', async () => {
    const user = userEvent.setup();
    const namedRow: WonOverRow = {
      ...baseRow,
      nameless: false,
      persona_id: 99,
      can_bind: false,
      can_take_into_service: true,
      can_send_away: true,
      can_settle: true,
    };

    renderWithProviders(<WonOverRows rows={[namedRow]} characterId={42} sceneId="7" />);

    await user.click(screen.getByText('Settle'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith('7', {
        action_key: 'settle',
        target_persona_id: 99,
      });
    });
  });

  it('Bind submit dispatches promote_summon with the chosen archetype, gift and name', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onSuccess({ backend: 'registry', deferred: false, success: true, message: 'Bound.' });
    });
    mockDispatch(mutate);
    mockUseCompanionArchetypes.mockReturnValue({
      data: [
        {
          id: 1,
          domain: 'bruiser',
          name: 'Sellsword',
          description: '',
          bind_difficulty: 2,
          capacity_cost: 1,
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useCompanionArchetypes>);
    mockUseCharacterGifts.mockReturnValue({
      data: [
        {
          id: 5,
          character: 42,
          gift: 9,
          gift_name: 'Watchful',
          gift_detail: { id: 9, name: 'Watchful' },
          acquired_at: '2026-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useCharacterGifts>);

    renderWithProviders(<WonOverRows rows={[baseRow]} characterId={42} sceneId="1" />);

    await user.click(screen.getByText('Bind as companion'));

    // Confirm starts disabled until archetype, gift, and name are all set.
    expect(screen.getByTestId('won-over-bind-confirm-7')).toBeDisabled();

    await user.selectOptions(screen.getByLabelText('Archetype'), '1');
    await user.selectOptions(screen.getByLabelText('Gift'), '9');
    await user.type(screen.getByLabelText('Companion name'), 'Pell');

    expect(screen.getByTestId('won-over-bind-confirm-7')).toBeEnabled();
    await user.click(screen.getByTestId('won-over-bind-confirm-7'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'promote_summon' },
          kwargs: { combat_opponent_id: 7, archetype_id: 1, gift_id: 9, name: 'Pell' },
        },
        expect.any(Object)
      );
    });
  });

  it('Take into service dispatches charm_asset with the chosen role_context', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onSuccess({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'Retained.',
      });
    });
    mockDispatch(mutate);

    const namedRow: WonOverRow = {
      ...baseRow,
      nameless: false,
      persona_id: 99,
      can_bind: false,
      can_take_into_service: true,
    };
    renderWithProviders(<WonOverRows rows={[namedRow]} characterId={42} sceneId="1" />);

    await user.click(screen.getByText('Take into service'));
    await user.selectOptions(screen.getByLabelText('Role'), 'informant');
    await user.click(screen.getByTestId('won-over-service-confirm-7'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'charm_asset' },
          kwargs: { target_persona_id: 99, role_context: 'informant' },
        },
        expect.any(Object)
      );
    });
  });
});
