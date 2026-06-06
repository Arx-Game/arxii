import { render, screen } from '@testing-library/react';
import { OwnedDwellingsCard } from './OwnedDwellingsCard';
import type { OwnedDwelling } from '../types';

function makeDwelling(overrides: Partial<OwnedDwelling> = {}): OwnedDwelling {
  return {
    id: 1,
    name: 'Vermillion Hall',
    polish_by_category: [],
    upkeep_warning: false,
    decayed_features_count: 0,
    dormant: false,
    dormant_since: null,
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

  it('shows upkeep-missed badge when upkeep_warning is true', () => {
    render(<OwnedDwellingsCard dwellings={[makeDwelling({ upkeep_warning: true })]} />);
    expect(screen.getByText(/upkeep missed/i)).toBeInTheDocument();
  });

  it('shows decayed-features count when > 0', () => {
    render(<OwnedDwellingsCard dwellings={[makeDwelling({ decayed_features_count: 3 })]} />);
    expect(screen.getByText(/3 decayed/i)).toBeInTheDocument();
  });

  it('shows dormant badge when dwelling is dormant', () => {
    render(
      <OwnedDwellingsCard
        dwellings={[makeDwelling({ dormant: true, dormant_since: '2026-01-15T00:00:00Z' })]}
      />
    );
    expect(screen.getByText(/Dormant/)).toBeInTheDocument();
  });

  it('suppresses the upkeep badge when dormant (dormant supersedes)', () => {
    render(
      <OwnedDwellingsCard
        dwellings={[
          makeDwelling({
            upkeep_warning: true,
            dormant: true,
            dormant_since: '2026-01-15T00:00:00Z',
          }),
        ]}
      />
    );
    expect(screen.queryByText(/upkeep missed/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Dormant/)).toBeInTheDocument();
  });
});
