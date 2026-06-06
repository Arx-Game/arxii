import { render, screen } from '@testing-library/react';
import { TenantedRoomsCard } from './TenantedRoomsCard';
import type { TenantedRoom } from '../types';

function makeRoom(overrides: Partial<TenantedRoom> = {}): TenantedRoom {
  return {
    id: 1,
    name: 'East Wing',
    polish_by_category: [],
    ...overrides,
  };
}

describe('TenantedRoomsCard', () => {
  it('shows empty state when persona tenants no rooms', () => {
    render(<TenantedRoomsCard rooms={[]} />);
    expect(screen.getByText(/tenants no rooms/i)).toBeInTheDocument();
  });

  it('renders one room with name', () => {
    render(<TenantedRoomsCard rooms={[makeRoom()]} />);
    expect(screen.getByText('East Wing')).toBeInTheDocument();
  });

  it('shows tier label next to category when one exists', () => {
    render(
      <TenantedRoomsCard
        rooms={[
          makeRoom({
            polish_by_category: [
              { category_id: 1, category_name: 'Elegance', value: 500, tier_label: 'Notable' },
            ],
          }),
        ]}
      />
    );
    expect(screen.getByText('Notable')).toBeInTheDocument();
    expect(screen.getByText('Elegance')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
  });

  it('shows polish without tier label when none is set', () => {
    render(
      <TenantedRoomsCard
        rooms={[
          makeRoom({
            polish_by_category: [
              { category_id: 1, category_name: 'Opulence', value: 100, tier_label: null },
            ],
          }),
        ]}
      />
    );
    expect(screen.getByText('Opulence')).toBeInTheDocument();
    expect(screen.queryByText('Notable')).not.toBeInTheDocument();
  });
});
