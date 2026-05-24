/**
 * Tests for ThreadPullPicker.
 *
 * Mocks:
 * - @/magic/queries (useApplicablePulls, useThreads)
 * - @/magic/api (previewPull)
 * - ./PullDetailModal (prevent Radix Dialog rendering issues in tests)
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks — must be hoisted before any imports that use the mocked modules
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/queries')>();
  return {
    ...actual,
    useApplicablePulls: vi.fn(),
    useThreads: vi.fn(),
  };
});

vi.mock('@/magic/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/api')>();
  return {
    ...actual,
    previewPull: vi.fn(),
  };
});

// Stub out PullDetailModal to avoid Radix Dialog complexity in unit tests.
vi.mock('../PullDetailModal', () => ({
  PullDetailModal: ({ open, thread }: { open: boolean; thread: { name: string } }) =>
    open ? <div data-testid="pull-detail-modal-stub">{thread.name}</div> : null,
}));

import * as magicQueries from '@/magic/queries';
import * as magicApi from '@/magic/api';
import { ThreadPullPicker } from '../ThreadPullPicker';
import type { ThreadPullPickerProps } from '../ThreadPullPicker';
import type { PullPreviewResponse, Thread, ThreadApplicability } from '@/magic/types';
import type { ApplicablePullsRequest } from '@/magic/types';

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

function makeThread(overrides: Partial<Thread> = {}): Thread {
  return {
    id: 1,
    owner: 100,
    resonance: 1,
    resonance_name: 'Bene',
    target_kind: 'FACET',
    name: 'Tidal Anchor',
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
  };
}

function makeApplicabilityRow(
  threadId: number,
  applicable: boolean,
  inapplicable_reason?: string
): ThreadApplicability {
  return {
    thread_id: threadId,
    applicable,
    inapplicable_reason: inapplicable_reason ?? null,
  };
}

function makePreviewResponse(overrides: Partial<PullPreviewResponse> = {}): PullPreviewResponse {
  return {
    resonance_cost: 4,
    anima_cost: 2,
    affordable: true,
    capped_intensity: false,
    resolved_effects: [],
    ...overrides,
  };
}

const DEFAULT_ACTION_CONTEXT: ApplicablePullsRequest = {
  character_sheet_id: 100,
  technique_id: 42,
};

function defaultProps(overrides?: Partial<ThreadPullPickerProps>): ThreadPullPickerProps {
  return {
    characterSheetId: 100,
    actionContext: DEFAULT_ACTION_CONTEXT,
    selectedPulls: {},
    onPullsChange: vi.fn(),
    showInapplicable: false,
    onToggleInapplicable: vi.fn(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const mockedUseApplicablePulls = magicQueries.useApplicablePulls as ReturnType<typeof vi.fn>;
const mockedUseThreads = magicQueries.useThreads as ReturnType<typeof vi.fn>;
const mockedPreviewPull = magicApi.previewPull as ReturnType<typeof vi.fn>;

function mockApplicable(rows: ThreadApplicability[]) {
  mockedUseApplicablePulls.mockReturnValue({ data: rows, isLoading: false, isError: false });
}

function mockThreads(threads: Thread[]) {
  mockedUseThreads.mockReturnValue({
    data: { results: threads, count: threads.length, next: null, previous: null },
    isLoading: false,
    isError: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedPreviewPull.mockResolvedValue(makePreviewResponse());
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ThreadPullPicker — applicable list renders', () => {
  it('renders thread names from the applicable list', async () => {
    const thread = makeThread({ id: 1, name: 'Tidal Anchor' });
    mockApplicable([makeApplicabilityRow(1, true)]);
    mockThreads([thread]);

    render(<ThreadPullPicker {...defaultProps()} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Tidal Anchor')).toBeInTheDocument();
    });
  });

  it('shows the applicable count in the header', async () => {
    const thread = makeThread({ id: 1, name: 'Vow Thread' });
    mockApplicable([makeApplicabilityRow(1, true)]);
    mockThreads([thread]);

    render(<ThreadPullPicker {...defaultProps()} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/1 applicable/)).toBeInTheDocument();
    });
  });

  it('shows "No applicable threads." when none are applicable', () => {
    mockApplicable([]);
    mockThreads([]);

    render(<ThreadPullPicker {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('no-applicable-threads')).toBeInTheDocument();
  });

  it('renders the tier strip for each applicable thread', async () => {
    const thread = makeThread({ id: 5, name: 'Test Thread' });
    mockApplicable([makeApplicabilityRow(5, true)]);
    mockThreads([thread]);

    render(<ThreadPullPicker {...defaultProps()} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('tier-btn-5-0')).toBeInTheDocument();
      expect(screen.getByTestId('tier-btn-5-1')).toBeInTheDocument();
      expect(screen.getByTestId('tier-btn-5-2')).toBeInTheDocument();
      expect(screen.getByTestId('tier-btn-5-3')).toBeInTheDocument();
    });
  });
});

describe('ThreadPullPicker — show-inapplicable toggle', () => {
  it('does not render inapplicable rows when toggle is off', async () => {
    const applicable = makeThread({ id: 1, name: 'Applicable Thread' });
    const inapplicable = makeThread({ id: 2, name: 'Inapplicable Thread' });
    mockApplicable([
      makeApplicabilityRow(1, true),
      makeApplicabilityRow(2, false, 'wrong_affinity'),
    ]);
    mockThreads([applicable, inapplicable]);

    render(
      <ThreadPullPicker {...defaultProps({ showInapplicable: false })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByText('Applicable Thread')).toBeInTheDocument();
    });
    expect(screen.queryByText('Inapplicable Thread')).not.toBeInTheDocument();
  });

  it('reveals inapplicable rows with reason chips when toggle is on', async () => {
    const applicable = makeThread({ id: 1, name: 'Applicable Thread' });
    const inapplicable = makeThread({ id: 2, name: 'Inapplicable Thread' });
    mockApplicable([
      makeApplicabilityRow(1, true),
      makeApplicabilityRow(2, false, 'anchored_on_other_technique'),
    ]);
    mockThreads([applicable, inapplicable]);

    render(
      <ThreadPullPicker {...defaultProps({ showInapplicable: true })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId('inapplicable-row-2')).toBeInTheDocument();
      expect(screen.getByTestId('inapplicable-reason-chip-2')).toBeInTheDocument();
    });
    // Reason chip text: underscores replaced with spaces
    expect(screen.getByTestId('inapplicable-reason-chip-2')).toHaveTextContent(
      'anchored on other technique'
    );
  });

  it('calls onToggleInapplicable when the checkbox is clicked', async () => {
    mockApplicable([]);
    mockThreads([]);
    const onToggleInapplicable = vi.fn();

    render(
      <ThreadPullPicker {...defaultProps({ onToggleInapplicable })} />,
      { wrapper: createWrapper() }
    );

    await userEvent.click(screen.getByTestId('show-inapplicable-toggle'));
    expect(onToggleInapplicable).toHaveBeenCalledWith(true);
  });
});

describe('ThreadPullPicker — tier selection', () => {
  it('calls onPullsChange with the new tier when a tier button is clicked', async () => {
    const thread = makeThread({ id: 3, name: 'Surging Tide' });
    mockApplicable([makeApplicabilityRow(3, true)]);
    mockThreads([thread]);
    const onPullsChange = vi.fn();

    render(
      <ThreadPullPicker {...defaultProps({ onPullsChange, selectedPulls: {} })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-3-2'));
    await userEvent.click(screen.getByTestId('tier-btn-3-2'));

    expect(onPullsChange).toHaveBeenCalledWith({ 3: 2 });
  });

  it('shows tier 0 selected by default (no entry in selectedPulls)', async () => {
    const thread = makeThread({ id: 4, name: 'Deep Current' });
    mockApplicable([makeApplicabilityRow(4, true)]);
    mockThreads([thread]);

    render(
      <ThreadPullPicker {...defaultProps({ selectedPulls: {} })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-4-0'));
    // Tier 0 should have the active/green styling
    const tier0Btn = screen.getByTestId('tier-btn-4-0');
    expect(tier0Btn).toHaveClass('bg-emerald-500/20');
  });
});

describe('ThreadPullPicker — all-tier previews on mount (Fix 1)', () => {
  it('fires previewPull for all 3 paid tiers on row mount', async () => {
    const thread = makeThread({ id: 7, name: 'Costly Pull', resonance: 5 });
    mockApplicable([makeApplicabilityRow(7, true)]);
    mockThreads([thread]);
    mockedPreviewPull.mockResolvedValue(makePreviewResponse());

    render(
      <ThreadPullPicker {...defaultProps({ selectedPulls: {} })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-7-0'));

    // All 3 paid tiers should have fired previewPull on mount.
    await waitFor(() => {
      expect(mockedPreviewPull).toHaveBeenCalledTimes(3);
    });
    expect(mockedPreviewPull).toHaveBeenCalledWith(
      expect.objectContaining({ tier: 1, resonance_id: 5 })
    );
    expect(mockedPreviewPull).toHaveBeenCalledWith(
      expect.objectContaining({ tier: 2, resonance_id: 5 })
    );
    expect(mockedPreviewPull).toHaveBeenCalledWith(
      expect.objectContaining({ tier: 3, resonance_id: 5 })
    );
  });

  it('disables an unaffordable tier before the user clicks it', async () => {
    const thread = makeThread({ id: 8, name: 'Costly Pull', resonance: 5, resonance_name: 'Sworn' });
    mockApplicable([makeApplicabilityRow(8, true)]);
    mockThreads([thread]);

    // Tier 1 unaffordable, tiers 2 and 3 affordable.
    mockedPreviewPull.mockImplementation(({ tier }: { tier: number }) => {
      if (tier === 1) {
        return Promise.resolve(makePreviewResponse({ affordable: false, resonance_cost: 5 }));
      }
      return Promise.resolve(makePreviewResponse({ affordable: true }));
    });

    render(
      <ThreadPullPicker
        {...defaultProps({
          selectedPulls: {},
          balanceByResonanceId: { 5: 4 },
        })}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-8-1'));

    // Wait for tier 1 preview to resolve and disable the button.
    await waitFor(() => {
      const tierBtn = screen.getByTestId('tier-btn-8-1');
      expect(tierBtn).toBeDisabled();
      expect(tierBtn).toHaveClass('opacity-60');
    });

    // Tooltip shows "Need X resonanceName; have Y"
    const tierBtn = screen.getByTestId('tier-btn-8-1');
    expect(tierBtn).toHaveAttribute('title', 'Need 5 Sworn; have 4');
  });

  it('leaves unresolved tiers tentatively enabled (null preview = not disabled)', async () => {
    const thread = makeThread({ id: 9, name: 'Slow Thread' });
    mockApplicable([makeApplicabilityRow(9, true)]);
    mockThreads([thread]);

    // previewPull never resolves — simulate pending state.
    mockedPreviewPull.mockReturnValue(new Promise(() => {}));

    render(
      <ThreadPullPicker {...defaultProps({ selectedPulls: {} })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-9-1'));

    // Tiers should be enabled while previews are pending.
    expect(screen.getByTestId('tier-btn-9-1')).not.toBeDisabled();
    expect(screen.getByTestId('tier-btn-9-2')).not.toBeDisabled();
    expect(screen.getByTestId('tier-btn-9-3')).not.toBeDisabled();
  });
});

describe('ThreadPullPicker — unaffordable tier (legacy — selected tier)', () => {
  it('shows unaffordable styling when preview returns affordable=false for selected tier', async () => {
    const thread = makeThread({ id: 7, name: 'Costly Pull' });
    mockApplicable([makeApplicabilityRow(7, true)]);
    mockThreads([thread]);
    mockedPreviewPull.mockResolvedValue(makePreviewResponse({ affordable: false }));

    render(
      <ThreadPullPicker {...defaultProps({ selectedPulls: { 7: 1 } })} />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByTestId('tier-btn-7-1'));

    // Wait for the preview to fire and resolve (no debounce now — resolves immediately).
    await waitFor(
      () => {
        const tierBtn = screen.getByTestId('tier-btn-7-1');
        // Unaffordable tier has muted styling and is disabled.
        expect(tierBtn).toHaveClass('opacity-60');
        expect(tierBtn).toBeDisabled();
      },
      { timeout: 1000 }
    );
  });
});

describe('ThreadPullPicker — auto-revert', () => {
  it('reverts paid pulls that become inapplicable when actionContext changes', async () => {
    const thread = makeThread({ id: 9, name: 'Reverting Thread' });
    // First render: thread 9 is applicable
    mockApplicable([makeApplicabilityRow(9, true)]);
    mockThreads([thread]);
    const onPullsChange = vi.fn();
    const onAutoRevertNotice = vi.fn();

    const { rerender } = render(
      <ThreadPullPicker
        {...defaultProps({
          selectedPulls: { 9: 2 },
          onPullsChange,
          onAutoRevertNotice,
        })}
      />,
      { wrapper: createWrapper() }
    );

    // Re-render with thread 9 now inapplicable
    mockApplicable([makeApplicabilityRow(9, false, 'wrong_affinity')]);

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThreadPullPicker
          characterSheetId={100}
          actionContext={{ character_sheet_id: 100, technique_id: 99 }}
          selectedPulls={{ 9: 2 }}
          onPullsChange={onPullsChange}
          showInapplicable={false}
          onToggleInapplicable={vi.fn()}
          onAutoRevertNotice={onAutoRevertNotice}
        />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(onPullsChange).toHaveBeenCalledWith({});
    });

    expect(onAutoRevertNotice).toHaveBeenCalledWith(
      expect.stringContaining('reverted to tier 0')
    );
  });

  it('does not revert tier-0 pulls even when thread becomes inapplicable', async () => {
    const thread = makeThread({ id: 10, name: 'Always Passive' });
    mockApplicable([makeApplicabilityRow(10, true)]);
    mockThreads([thread]);
    const onPullsChange = vi.fn();

    const { rerender } = render(
      <ThreadPullPicker
        {...defaultProps({
          selectedPulls: { 10: 0 },
          onPullsChange,
        })}
      />,
      { wrapper: createWrapper() }
    );

    mockApplicable([makeApplicabilityRow(10, false, 'wrong_affinity')]);

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThreadPullPicker
          characterSheetId={100}
          actionContext={{ character_sheet_id: 100, technique_id: 99 }}
          selectedPulls={{ 10: 0 }}
          onPullsChange={onPullsChange}
          showInapplicable={false}
          onToggleInapplicable={vi.fn()}
        />
      </QueryClientProvider>
    );

    // Tier 0 should NOT trigger a revert call
    await new Promise((r) => setTimeout(r, 50));
    expect(onPullsChange).not.toHaveBeenCalled();
  });
});

describe('ThreadPullPicker — details affordance', () => {
  it('opens the detail modal when the details button is clicked', async () => {
    const thread = makeThread({ id: 6, name: 'Deep Tide' });
    mockApplicable([makeApplicabilityRow(6, true)]);
    mockThreads([thread]);
    // selected tier 1 so the cost+details row renders
    mockedPreviewPull.mockResolvedValue(makePreviewResponse({ resonance_cost: 3, anima_cost: 1 }));

    render(
      <ThreadPullPicker {...defaultProps({ selectedPulls: { 6: 1 } })} />,
      { wrapper: createWrapper() }
    );

    // Wait for preview to load and details button to appear
    await waitFor(
      () => {
        expect(screen.getByTestId('details-btn-6')).toBeInTheDocument();
      },
      { timeout: 1000 }
    );

    await userEvent.click(screen.getByTestId('details-btn-6'));

    expect(screen.getByTestId('pull-detail-modal-stub')).toBeInTheDocument();
    expect(screen.getByTestId('pull-detail-modal-stub')).toHaveTextContent('Deep Tide');
  });
});
