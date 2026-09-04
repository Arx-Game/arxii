/**
 * ReadinessStrip tests (#3561).
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ReadinessStrip } from '../../components/stakes/ReadinessStrip';

vi.mock('../../queries', () => ({
  useBeatReadiness: vi.fn(),
  useOpenBeatActivation: vi.fn(),
}));

import * as queries from '../../queries';

function mockReadiness(data: unknown) {
  vi.mocked(queries.useBeatReadiness).mockReturnValue({
    data,
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockActivation(data: unknown) {
  vi.mocked(queries.useOpenBeatActivation).mockReturnValue({
    data,
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

describe('ReadinessStrip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the ready verdict with declared/effective risk', () => {
    mockReadiness({
      is_staked: true,
      is_ready: true,
      problems: [],
      advisories: [],
      declared_risk: 'moderate',
      effective_risk: 'moderate',
      locked: false,
      locked_at: null,
    });
    mockActivation(undefined);

    renderWithProviders(<ReadinessStrip beatId={200} />);

    expect(screen.getByTestId('stakes-readiness-verdict')).toHaveTextContent('Ready');
    expect(screen.getByText(/Declared risk: Moderate/)).toBeInTheDocument();
    expect(screen.getByText(/Effective risk: Moderate/)).toBeInTheDocument();
    expect(screen.queryByTestId('stakes-lock-banner')).not.toBeInTheDocument();
  });

  it('renders problems and advisories when not ready', () => {
    mockReadiness({
      is_staked: true,
      is_ready: false,
      problems: ['No WIN branch authored'],
      advisories: ['Reward total is below the calibration floor'],
      declared_risk: 'high',
      effective_risk: 'none',
      locked: false,
      locked_at: null,
    });
    mockActivation(undefined);

    renderWithProviders(<ReadinessStrip beatId={200} />);

    expect(screen.getByTestId('stakes-readiness-verdict')).toHaveTextContent('Not ready');
    expect(screen.getByTestId('stakes-readiness-problems')).toHaveTextContent(
      'No WIN branch authored'
    );
    expect(screen.getByTestId('stakes-readiness-advisories')).toHaveTextContent(
      'Reward total is below the calibration floor'
    );
  });

  it('shows the lock banner when an open activation exists', () => {
    mockReadiness({
      is_staked: true,
      is_ready: true,
      problems: [],
      advisories: [],
      declared_risk: 'moderate',
      effective_risk: 'moderate',
      locked: true,
      locked_at: '2026-09-01T00:00:00Z',
    });
    mockActivation([{ id: 1, beat: 200, locked_at: '2026-09-01T00:00:00Z' }]);

    renderWithProviders(<ReadinessStrip beatId={200} />);

    expect(screen.getByTestId('stakes-lock-banner')).toHaveTextContent(
      'Locked while the scene runs'
    );
  });
});
