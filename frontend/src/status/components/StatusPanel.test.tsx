import { screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StatusPanel } from './StatusPanel';
import type { CharacterVitalsData } from '@/vitals/vitalsQueries';

vi.mock('@/vitals/vitalsQueries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/vitals/vitalsQueries')>()),
  useCharacterVitalsQuery: vi.fn(),
}));
vi.mock('@/magic/queries', () => ({
  useCharacterAnima: vi.fn(),
  useCharacterResonances: vi.fn(),
}));
vi.mock('../queries', () => ({
  useCharacterPurse: vi.fn(),
  useActionPoints: vi.fn(),
}));

import { useCharacterVitalsQuery } from '@/vitals/vitalsQueries';
import { useCharacterAnima, useCharacterResonances } from '@/magic/queries';
import { useActionPoints, useCharacterPurse } from '../queries';

const mockVitals = vi.mocked(useCharacterVitalsQuery);
const mockAnima = vi.mocked(useCharacterAnima);
const mockResonances = vi.mocked(useCharacterResonances);
const mockPurse = vi.mocked(useCharacterPurse);
const mockActionPoints = vi.mocked(useActionPoints);

const VITALS: CharacterVitalsData = {
  health: 40,
  max_health: 100,
  health_percentage: 0.4,
  wound_description: 'Badly wounded',
  status: 'alive',
  fatigue: {
    physical: { current: 2, capacity: 10, percentage: 20, zone: 'strained' },
    social: { current: 0, capacity: 8, percentage: 0, zone: 'fresh' },
    mental: { current: 0, capacity: 8, percentage: 0, zone: 'tired' },
    well_rested: false,
    rested_today: false,
  },
};

function setQueries({
  vitals = VITALS,
  isLoading = false,
  anima = { id: 1, character: 7, current: 30, maximum: 50, last_recovery: null, band: 'steady' },
  resonances = [],
  purse = { balance: 347 },
  actionPoints = { current: 3, effective_maximum: 5, banked: 0 },
}: {
  vitals?: CharacterVitalsData | null;
  isLoading?: boolean;
  anima?: unknown;
  resonances?: unknown[];
  purse?: unknown;
  actionPoints?: unknown;
} = {}) {
  mockVitals.mockReturnValue({
    data: vitals,
    isLoading,
  } as unknown as ReturnType<typeof useCharacterVitalsQuery>);
  mockAnima.mockReturnValue({
    data: anima,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterAnima>);
  mockResonances.mockReturnValue({
    data: resonances,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterResonances>);
  mockPurse.mockReturnValue({
    data: purse,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterPurse>);
  mockActionPoints.mockReturnValue({
    data: actionPoints,
    isLoading: false,
  } as unknown as ReturnType<typeof useActionPoints>);
}

describe('StatusPanel', () => {
  beforeEach(() => {
    mockVitals.mockReset();
    mockAnima.mockReset();
    mockResonances.mockReset();
    mockPurse.mockReset();
    mockActionPoints.mockReset();
  });

  it('renders wound description as words, never a numeric health fraction', () => {
    setQueries();
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText('Badly wounded')).toBeInTheDocument();
    expect(screen.queryByText(/\d+\s*\/\s*\d+/)).not.toBeInTheDocument();
  });

  it('renders fatigue zone words per pool', () => {
    setQueries();
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText(/Physical:\s*strained/i)).toBeInTheDocument();
    expect(screen.getByText(/Social:\s*fresh/i)).toBeInTheDocument();
    expect(screen.getByText(/Mental:\s*tired/i)).toBeInTheDocument();
  });

  it('renders the anima band word', () => {
    setQueries();
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText('steady')).toBeInTheDocument();
  });

  it('renders resonance names, muted, and an empty-state line when none', () => {
    setQueries({ resonances: [] });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText('No resonances yet.')).toBeInTheDocument();
  });

  it('renders resonance names when present', () => {
    setQueries({
      resonances: [
        { id: 1, character_sheet: 7, resonance: 1, resonance_name: 'Grief', claimed_at: '' },
      ],
    });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText('Grief')).toBeInTheDocument();
  });

  it('renders the coin line via formatCoppers', () => {
    setQueries({ purse: { balance: 347 } });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText('3g 4s 7c')).toBeInTheDocument();
  });

  it('renders the AP line as "N of M this week"', () => {
    setQueries({ actionPoints: { current: 3, effective_maximum: 5, banked: 0 } });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText(/3 of 5 this week/)).toBeInTheDocument();
  });

  it('shows banked AP when nonzero', () => {
    setQueries({ actionPoints: { current: 3, effective_maximum: 5, banked: 2 } });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByText(/\(\+2 banked\)/)).toBeInTheDocument();
  });

  it('renders nothing when the viewer lacks permission (null vitals)', () => {
    setQueries({ vitals: null });
    const { container } = renderWithProviders(<StatusPanel characterId={7} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a loading skeleton while the vitals query is in flight', () => {
    setQueries({ vitals: null, isLoading: true });
    renderWithProviders(<StatusPanel characterId={7} />);
    expect(screen.getByTestId('status-panel-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('status-panel')).not.toBeInTheDocument();
  });
});
