import { screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { VitalsPanel } from '../components/VitalsPanel';
import type { CharacterVitalsData } from '../vitalsQueries';

vi.mock('../vitalsQueries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../vitalsQueries')>()),
  useCharacterVitalsQuery: vi.fn(),
}));
vi.mock('@/magic/queries', () => ({ useCharacterAnima: vi.fn() }));
import { useCharacterVitalsQuery } from '../vitalsQueries';
import { useCharacterAnima } from '@/magic/queries';

const mockVitalsQuery = vi.mocked(useCharacterVitalsQuery);
const mockAnima = vi.mocked(useCharacterAnima);

const VITALS: CharacterVitalsData = {
  health: 40,
  max_health: 100,
  health_percentage: 0.4,
  wound_description: 'Badly wounded',
  status: 'alive',
  fatigue: {
    physical: { current: 2, capacity: 10, percentage: 20, zone: 'fresh' },
    social: { current: 0, capacity: 8, percentage: 0, zone: 'fresh' },
    mental: { current: 0, capacity: 8, percentage: 0, zone: 'fresh' },
    well_rested: false,
    rested_today: false,
  },
};

function setQueries(vitals: CharacterVitalsData | null, anima: unknown) {
  mockVitalsQuery.mockReturnValue({
    data: vitals,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterVitalsQuery>);
  mockAnima.mockReturnValue({
    data: anima,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterAnima>);
}

describe('VitalsPanel', () => {
  beforeEach(() => {
    mockVitalsQuery.mockReset();
    mockAnima.mockReset();
  });

  it('renders health, wound description, status badge, anima, and fatigue', () => {
    setQueries(VITALS, { id: 1, character: 7, current: 30, maximum: 50, last_recovery: null });
    renderWithProviders(<VitalsPanel characterId={7} />);
    expect(screen.getByTestId('vitals-panel')).toBeInTheDocument();
    expect(screen.getByText('40/100')).toBeInTheDocument();
    expect(screen.getByText('Badly wounded')).toBeInTheDocument();
    expect(screen.getByText('alive')).toBeInTheDocument();
    expect(screen.getByText('30/50')).toBeInTheDocument();
    expect(screen.getByText('Physical')).toBeInTheDocument();
  });

  it('renders nothing when the viewer lacks permission (null data)', () => {
    setQueries(null, null);
    const { container } = renderWithProviders(<VitalsPanel characterId={7} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('omits the anima bar when no anima record exists', () => {
    setQueries(VITALS, null);
    renderWithProviders(<VitalsPanel characterId={7} />);
    expect(screen.getByTestId('vitals-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('vitals-anima')).not.toBeInTheDocument();
  });
});
