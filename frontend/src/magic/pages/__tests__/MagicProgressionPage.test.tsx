import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ProgressionStage, MagicProgressionResponse } from '@/magic/magicProgressionTypes';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/magicProgressionQueries', () => ({
  useMagicProgression: vi.fn(),
}));

// MagicProgressionPage resolves the active character via Redux + roster —
// same pattern as ThreadHubPage. Stub both so the component renders without
// a real Redux Provider or roster fetch.
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn(() => null),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({ data: [] })),
}));

// StageSection renders sub-components; stub it to isolate the page logic.
vi.mock('@/magic/components/progression/StageSection', () => ({
  StageSection: ({ stage }: { stage: ProgressionStage }) => (
    <div data-testid={`stage-section-${stage.stage}`}>{stage.stage_label}</div>
  ),
}));

import * as progressionQueries from '@/magic/magicProgressionQueries';
import { MagicProgressionPage } from '../MagicProgressionPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

type UseQueryReturn<T> = {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: null | Error;
};

function makeQueryResult<T>(
  data: T | undefined,
  loading = false,
  isError = false,
  error: null | Error = null
): UseQueryReturn<T> {
  return { data, isLoading: loading, isError, error };
}

function makeStage(overrides: Partial<ProgressionStage> = {}): ProgressionStage {
  return {
    stage: 1,
    stage_label: 'Stage 1',
    is_current: false,
    has_undiscovered: false,
    milestones: [],
    ...overrides,
  };
}

function make6StagePayload(): MagicProgressionResponse {
  return {
    stages: [1, 2, 3, 4, 5, 6].map((n) =>
      makeStage({ stage: n, stage_label: `Stage ${n}`, is_current: n === 2 })
    ),
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(progressionQueries.useMagicProgression).mockReturnValue(
    makeQueryResult(make6StagePayload()) as ReturnType<
      typeof progressionQueries.useMagicProgression
    >
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MagicProgressionPage', () => {
  it('renders the page heading', () => {
    render(<MagicProgressionPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('heading', { name: 'Magic Progression' })).toBeInTheDocument();
  });

  it('renders a loading skeleton grid while data is loading', () => {
    vi.mocked(progressionQueries.useMagicProgression).mockReturnValue(
      makeQueryResult(undefined, true) as ReturnType<typeof progressionQueries.useMagicProgression>
    );

    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('heading', { name: 'Magic Progression' })).toBeInTheDocument();
    const skeletons = document.querySelectorAll('.animate-pulse, [class*="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders an error message when the query errors', () => {
    vi.mocked(progressionQueries.useMagicProgression).mockReturnValue(
      makeQueryResult(undefined, false, true, new Error('Network failure')) as ReturnType<
        typeof progressionQueries.useMagicProgression
      >
    );

    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Network failure')).toBeInTheDocument();
  });

  it('renders 6 StageSections for a 6-stage payload', () => {
    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    for (let n = 1; n <= 6; n++) {
      expect(screen.getByTestId(`stage-section-${n}`)).toBeInTheDocument();
    }
  });

  it('renders stage labels from the payload', () => {
    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    for (let n = 1; n <= 6; n++) {
      expect(screen.getByText(`Stage ${n}`)).toBeInTheDocument();
    }
  });

  it('renders nothing but the heading when stages array is empty', () => {
    vi.mocked(progressionQueries.useMagicProgression).mockReturnValue(
      makeQueryResult({ stages: [] }) as ReturnType<typeof progressionQueries.useMagicProgression>
    );

    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('heading', { name: 'Magic Progression' })).toBeInTheDocument();
    expect(document.querySelectorAll('[data-testid^="stage-section-"]').length).toBe(0);
  });

  it('shows a generic error message when error is not an Error instance', () => {
    vi.mocked(progressionQueries.useMagicProgression).mockReturnValue(
      makeQueryResult(undefined, false, true, null) as ReturnType<
        typeof progressionQueries.useMagicProgression
      >
    );

    render(<MagicProgressionPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Failed to load magic progression.')).toBeInTheDocument();
  });
});
