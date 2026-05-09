import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Thread } from '../../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useImbueThread: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { ImbuePanel } from '../ImbuePanel';

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
  path_cap: 20,
  anchor_cap: 20,
  effective_cap: 20,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  ...overrides,
});

type MutationState = {
  mutate: ReturnType<typeof vi.fn>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  isSuccess: boolean;
};

function makeMutation(overrides: Partial<MutationState> = {}): MutationState {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(magicQueries.useImbueThread).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.useImbueThread>
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ImbuePanel', () => {
  it('renders the panel with default amount of 1', () => {
    render(<ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('imbue-panel')).toBeInTheDocument();
    expect(screen.getByTestId('imbue-amount').textContent).toBe('1');
  });

  it('renders balance in description', () => {
    render(<ImbuePanel thread={makeThread()} balance={7} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText(/Available balance:/)).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('calls mutate with correct args when Imbue is clicked', () => {
    const mockMutate = vi.fn();
    vi.mocked(magicQueries.useImbueThread).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.useImbueThread
      >
    );

    render(<ImbuePanel thread={makeThread({ id: 5 })} balance={10} characterSheetId={200} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByTestId('imbue-button'));

    expect(mockMutate).toHaveBeenCalledOnce();
    expect(mockMutate).toHaveBeenCalledWith(
      { characterSheetId: 200, threadId: 5, amount: 1 },
      expect.any(Object)
    );
  });

  it('increments and decrements amount', () => {
    render(<ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByTestId('imbue-increment'));
    expect(screen.getByTestId('imbue-amount').textContent).toBe('2');

    fireEvent.click(screen.getByTestId('imbue-decrement'));
    expect(screen.getByTestId('imbue-amount').textContent).toBe('1');
  });

  it('does not allow amount below 0', () => {
    render(<ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    // Decrement from 1 to 0
    fireEvent.click(screen.getByTestId('imbue-decrement'));
    expect(screen.getByTestId('imbue-amount').textContent).toBe('0');

    // Decrement button should now be disabled at 0
    expect(screen.getByTestId('imbue-decrement')).toBeDisabled();
  });

  it('does not allow amount above balance', () => {
    render(<ImbuePanel thread={makeThread()} balance={3} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    // Increment to 3 (balance)
    fireEvent.click(screen.getByTestId('imbue-increment'));
    fireEvent.click(screen.getByTestId('imbue-increment'));
    expect(screen.getByTestId('imbue-amount').textContent).toBe('3');

    // Increment button should be disabled at max
    expect(screen.getByTestId('imbue-increment')).toBeDisabled();
  });

  it('shows error message inline when mutation fails', () => {
    vi.mocked(magicQueries.useImbueThread).mockReturnValue(
      makeMutation({
        isError: true,
        error: new Error('Insufficient resonance'),
      }) as unknown as ReturnType<typeof magicQueries.useImbueThread>
    );

    render(<ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('imbue-error')).toBeInTheDocument();
    expect(screen.getByText('Insufficient resonance')).toBeInTheDocument();
  });

  it('calls onResult callback after successful mutation', async () => {
    const onResult = vi.fn();
    const mockMutate = vi
      .fn()
      .mockImplementation((_vars, opts: { onSuccess?: (r: unknown) => void }) => {
        opts?.onSuccess?.({ success: true, levels_gained: 1, new_level: 20 });
      });

    vi.mocked(magicQueries.useImbueThread).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.useImbueThread
      >
    );

    render(
      <ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} onResult={onResult} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByTestId('imbue-button'));

    await waitFor(() => {
      expect(onResult).toHaveBeenCalledOnce();
      expect(onResult).toHaveBeenCalledWith({ success: true, levels_gained: 1, new_level: 20 });
    });
  });

  it('shows result summary after successful mutation', async () => {
    const mockMutate = vi
      .fn()
      .mockImplementation((_vars, opts: { onSuccess?: (r: unknown) => void }) => {
        opts?.onSuccess?.({
          success: true,
          levels_gained: 2,
          new_level: 30,
          blocked_by: 'NONE',
        });
      });

    vi.mocked(magicQueries.useImbueThread).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.useImbueThread
      >
    );

    render(<ImbuePanel thread={makeThread()} balance={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByTestId('imbue-button'));

    await waitFor(() => {
      expect(screen.getByTestId('imbue-result')).toBeInTheDocument();
      expect(screen.getByTestId('imbue-levels-gained')).toBeInTheDocument();
    });
  });
});
