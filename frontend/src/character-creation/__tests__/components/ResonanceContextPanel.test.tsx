/**
 * ResonanceContextPanel Component Tests
 *
 * Tests for the ResonanceContextPanel component which displays projected
 * resonances from distinctions during character creation.
 */

import { screen } from '@testing-library/react';
import { ResonanceContextPanel } from '../../components/magic/ResonanceContextPanel';
import type { ProjectedResonance } from '../../types';
import { createTestQueryClient, renderWithCharacterCreationProviders } from '../testUtils';

const mockProjectedResonances: ProjectedResonance[] = [
  {
    resonance_id: 1,
    resonance_name: 'Shadow',
    total: 20,
    sources: [
      { distinction_name: 'Nightborn', value: 10 },
      { distinction_name: 'Umbral Initiate', value: 10 },
    ],
  },
  {
    resonance_id: 2,
    resonance_name: 'Flame',
    total: 10,
    sources: [{ distinction_name: 'Firebrand', value: 10 }],
  },
];

describe('ResonanceContextPanel', () => {
  describe('Rendering', () => {
    it('displays resonance names and totals', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ResonanceContextPanel projectedResonances={mockProjectedResonances} />,
        { queryClient }
      );

      expect(screen.getByText('Your Resonances')).toBeInTheDocument();
      expect(screen.getByText('Shadow')).toBeInTheDocument();
      expect(screen.getByText('+20')).toBeInTheDocument();
      expect(screen.getByText('Flame')).toBeInTheDocument();
      expect(screen.getByText('+10')).toBeInTheDocument();
    });

    it('displays source breakdown text', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ResonanceContextPanel projectedResonances={mockProjectedResonances} />,
        { queryClient }
      );

      expect(screen.getByText('Nightborn (+10)')).toBeInTheDocument();
      expect(screen.getByText('Umbral Initiate (+10)')).toBeInTheDocument();
      expect(screen.getByText('Firebrand (+10)')).toBeInTheDocument();
    });

    it('shows empty message when no resonances', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<ResonanceContextPanel projectedResonances={[]} />, {
        queryClient,
      });

      expect(screen.getByText('No resonances from distinctions')).toBeInTheDocument();
    });

    it('shows loading state', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ResonanceContextPanel projectedResonances={undefined} isLoading={true} />,
        { queryClient }
      );

      const pulseElements = document.querySelectorAll('.animate-pulse');
      expect(pulseElements.length).toBe(2);
    });
  });
});
