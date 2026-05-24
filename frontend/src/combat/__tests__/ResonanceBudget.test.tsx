/**
 * Tests for ResonanceBudget rail section.
 *
 * Mocks useCharacterResonances to avoid network calls.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useCharacterResonances: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { ResonanceBudget } from '../sections/ResonanceBudget';
import type { CharacterResonance } from '@/magic/types';

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

const mockedUseCharacterResonances = magicQueries.useCharacterResonances as ReturnType<
  typeof vi.fn
>;

function makeResonance(overrides: Partial<CharacterResonance> = {}): CharacterResonance {
  return {
    id: 1,
    character_sheet: 10,
    resonance: 5,
    resonance_name: 'Flame',
    resonance_detail: {
      id: 5,
      name: 'Flame',
    } as CharacterResonance['resonance_detail'],
    balance: 3,
    lifetime_earned: 10,
    claimed_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ResonanceBudget', () => {
  it('renders loading state while resonances load', () => {
    mockedUseCharacterResonances.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    render(<ResonanceBudget characterSheetId={10} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('resonance-loading')).toBeInTheDocument();
  });

  it('renders error state when resonances fail', () => {
    mockedUseCharacterResonances.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(<ResonanceBudget characterSheetId={10} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('resonance-error')).toBeInTheDocument();
  });

  it('renders empty message when no resonances', () => {
    mockedUseCharacterResonances.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });

    render(<ResonanceBudget characterSheetId={10} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('resonance-empty')).toBeInTheDocument();
  });

  it('renders one row per resonance with name and balance', () => {
    const resonances: CharacterResonance[] = [
      makeResonance({ id: 1, resonance_name: 'Flame', balance: 3, lifetime_earned: 10 }),
      makeResonance({ id: 2, resonance_name: 'Tide', balance: 7, lifetime_earned: 20 }),
    ];
    mockedUseCharacterResonances.mockReturnValue({
      data: resonances,
      isLoading: false,
      isError: false,
    });

    render(<ResonanceBudget characterSheetId={10} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('resonance-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('resonance-row-2')).toBeInTheDocument();
    expect(screen.getByText('Flame')).toBeInTheDocument();
    expect(screen.getByText('Tide')).toBeInTheDocument();
  });

  it('renders bars for each resonance', () => {
    const resonances: CharacterResonance[] = [
      makeResonance({ id: 1, resonance_name: 'Flame', balance: 5, lifetime_earned: 10 }),
    ];
    mockedUseCharacterResonances.mockReturnValue({
      data: resonances,
      isLoading: false,
      isError: false,
    });

    render(<ResonanceBudget characterSheetId={10} />, { wrapper: createWrapper() });

    const bar = screen.getByTestId('resonance-bar-1');
    expect(bar).toBeInTheDocument();
    // 5/10 = 50%
    expect(bar).toHaveStyle({ width: '50%' });
  });

  it('collapses content when collapsed=true', () => {
    mockedUseCharacterResonances.mockReturnValue({
      data: [makeResonance({ id: 1 })],
      isLoading: false,
      isError: false,
    });

    render(<ResonanceBudget characterSheetId={10} collapsed={true} />, {
      wrapper: createWrapper(),
    });

    // Row should not be visible when collapsed
    expect(screen.queryByTestId('resonance-row-1')).not.toBeInTheDocument();
  });

  it('calls onToggleCollapse when header is clicked', async () => {
    const user = userEvent.setup();
    mockedUseCharacterResonances.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });

    const onToggle = vi.fn();
    render(<ResonanceBudget characterSheetId={10} onToggleCollapse={onToggle} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('resonance-budget-toggle'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
