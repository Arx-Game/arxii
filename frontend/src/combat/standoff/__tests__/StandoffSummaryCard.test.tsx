import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StandoffSummaryCard } from '../StandoffSummaryCard';

describe('StandoffSummaryCard', () => {
  it('lists each group with count and state chips, and the participants', () => {
    render(
      <StandoffSummaryCard
        summary={{
          place: 'the Corle gate',
          participants: ['Aubrin Rennick', 'Wrenna Harrin'],
          groups: [
            {
              group_id: 1,
              name: 'Sellswords',
              member_count: 6,
              state: 'open',
              morale_state: 'falter',
              emboldened: true,
            },
            {
              group_id: 2,
              name: 'Maud',
              member_count: 1,
              state: 'settled',
              morale_state: 'steady',
              emboldened: false,
            },
          ],
        }}
      />
    );
    expect(screen.getByRole('heading', { name: /Standoff at the Corle gate/ })).toBeInTheDocument();
    expect(screen.getByText('Sellswords')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('emboldened')).toBeInTheDocument();
    expect(screen.getByText('Faltering')).toBeInTheDocument();
    expect(screen.getByText('settled')).toBeInTheDocument();
    expect(screen.getByText('In the standoff: Aubrin Rennick, Wrenna Harrin.')).toBeInTheDocument();
  });
});
