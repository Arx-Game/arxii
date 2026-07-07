import { render, screen } from '@testing-library/react';
import { OwnedDwellingsCard } from './OwnedDwellingsCard';
import type { OwnedDwelling } from '../types';

function makeDwelling(overrides: Partial<OwnedDwelling> = {}): OwnedDwelling {
  return {
    id: 1,
    name: 'Vermillion Hall',
    polish_by_category: [],
    condition_label: 'Excellent',
    ...overrides,
  };
}

describe('OwnedDwellingsCard', () => {
  it('shows empty state when persona owns no buildings', () => {
    render(<OwnedDwellingsCard dwellings={[]} />);
    expect(screen.getByText(/owns no buildings/i)).toBeInTheDocument();
  });

  it('renders one building with name', () => {
    render(<OwnedDwellingsCard dwellings={[makeDwelling()]} />);
    expect(screen.getByText('Vermillion Hall')).toBeInTheDocument();
  });

  it('shows tier label next to category when one exists', () => {
    render(
      <OwnedDwellingsCard
        dwellings={[
          makeDwelling({
            polish_by_category: [
              { category_id: 1, category_name: 'Opulence', value: 2500, tier_label: 'Grand' },
            ],
          }),
        ]}
      />
    );
    expect(screen.getByText('Grand')).toBeInTheDocument();
    expect(screen.getByText('Opulence')).toBeInTheDocument();
    expect(screen.getByText('2,500')).toBeInTheDocument();
  });

  it('shows polish without tier label when none is set', () => {
    render(
      <OwnedDwellingsCard
        dwellings={[
          makeDwelling({
            polish_by_category: [
              { category_id: 1, category_name: 'Elegance', value: 100, tier_label: null },
            ],
          }),
        ]}
      />
    );
    expect(screen.getByText('Elegance')).toBeInTheDocument();
    expect(screen.queryByText('Grand')).not.toBeInTheDocument();
  });

  it('shows the condition label badge', () => {
    render(<OwnedDwellingsCard dwellings={[makeDwelling({ condition_label: 'Ramshackle' })]} />);
    expect(screen.getByText('Ramshackle')).toBeInTheDocument();
  });
});
