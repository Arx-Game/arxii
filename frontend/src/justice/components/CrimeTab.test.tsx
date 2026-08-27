/**
 * CrimeTab / MyCaseCard sentence-countdown tests (#2378 Task 8).
 *
 * Mirrors MotifStylePanel.test.tsx's idiom: mock the '../queries' module
 * (no msw), render with providers, assert on data-testid hooks.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CrimeTab } from './CrimeTab';
import type { MyCase } from '../api';
import type {
  useBribeMutation,
  useInitiateTrialMutation,
  useLieLowMutation,
  useMyCase,
  usePersonaHeat,
} from '../queries';

vi.mock('../queries', () => ({
  usePersonaHeat: vi.fn(),
  useMyCase: vi.fn(),
  useInitiateTrialMutation: vi.fn(),
  useLieLowMutation: vi.fn(),
  useBribeMutation: vi.fn(),
}));

import * as justiceQueries from '../queries';

const baseCase: MyCase = {
  id: 1,
  area_name: 'Arx',
  society_name: 'City Watch',
  opened_at: '2026-08-01T00:00:00Z',
  evidence_total: 0,
  release_threshold: 3,
  failed_outs: 0,
  sentence_kind: '',
  sentence_amount: 0,
  sentence_ends_at: null,
  terminal_due_at: null,
};

function setupMocks(options?: { myCase?: MyCase | null; trialMutate?: ReturnType<typeof vi.fn> }) {
  vi.mocked(justiceQueries.usePersonaHeat).mockReturnValue({
    data: [],
    isLoading: false,
  } as unknown as ReturnType<typeof usePersonaHeat>);

  vi.mocked(justiceQueries.useMyCase).mockReturnValue({
    data: options?.myCase === undefined ? null : options.myCase,
  } as unknown as ReturnType<typeof useMyCase>);

  vi.mocked(justiceQueries.useInitiateTrialMutation).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
    mutate: options?.trialMutate ?? vi.fn(),
  } as unknown as ReturnType<typeof useInitiateTrialMutation>);

  vi.mocked(justiceQueries.useLieLowMutation).mockReturnValue({
    isPending: false,
    isError: false,
    error: null,
    mutate: vi.fn(),
  } as unknown as ReturnType<typeof useLieLowMutation>);

  vi.mocked(justiceQueries.useBribeMutation).mockReturnValue({
    isPending: false,
    isError: false,
    error: null,
    mutate: vi.fn(),
  } as unknown as ReturnType<typeof useBribeMutation>);
}

describe('MyCaseCard sentence countdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-26T00:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing extra pre-verdict (blank sentence_kind)', () => {
    setupMocks({ myCase: baseCase });
    renderWithProviders(<CrimeTab viewerEntryId={7} />);

    expect(screen.getByTestId('my-case-card')).toBeInTheDocument();
    expect(screen.queryByTestId('sentence-countdown')).not.toBeInTheDocument();
    expect(screen.queryByTestId('terminal-countdown')).not.toBeInTheDocument();
    // Pre-verdict: the trial call-to-action still shows.
    expect(screen.getByText('Stand trial now')).toBeInTheDocument();
  });

  it('renders a brig-term countdown in days remaining, and hides the trial button', () => {
    setupMocks({
      myCase: {
        ...baseCase,
        sentence_kind: 'brig_term',
        sentence_amount: 5,
        sentence_ends_at: '2026-08-29T00:00:00Z',
      },
    });
    renderWithProviders(<CrimeTab viewerEntryId={7} />);

    expect(screen.getByTestId('sentence-countdown')).toHaveTextContent('Serving: 3 days remain');
    expect(screen.queryByText('Stand trial now')).not.toBeInTheDocument();
  });

  it('renders an exile-until date', () => {
    setupMocks({
      myCase: {
        ...baseCase,
        sentence_kind: 'exile',
        sentence_amount: 30,
        sentence_ends_at: '2026-09-25T00:00:00Z',
      },
    });
    renderWithProviders(<CrimeTab viewerEntryId={7} />);

    expect(screen.getByTestId('sentence-countdown')).toHaveTextContent('Exiled until');
  });

  it('renders the terminal rescue-window countdown', () => {
    setupMocks({
      myCase: {
        ...baseCase,
        sentence_kind: 'execution',
        terminal_due_at: '2026-08-29T00:00:00Z',
      },
    });
    renderWithProviders(<CrimeTab viewerEntryId={7} />);

    expect(screen.getByTestId('terminal-countdown')).toHaveTextContent('3 days');
    expect(screen.queryByTestId('sentence-countdown')).not.toBeInTheDocument();
  });

  it('renders nothing when the viewer has no open/active case', () => {
    setupMocks({ myCase: null });
    renderWithProviders(<CrimeTab viewerEntryId={7} />);

    expect(screen.queryByTestId('my-case-card')).not.toBeInTheDocument();
  });
});
