import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { LocationsTab } from './LocationsTab';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RenownPayload } from '@/renown/types';
import type { MyShip } from '../api';

vi.mock('@/renown/queries', () => ({
  usePersonaRenownQuery: vi.fn(),
}));
vi.mock('../queries', () => ({
  useMyShipsQuery: vi.fn(),
}));

import { usePersonaRenownQuery } from '@/renown/queries';
import { useMyShipsQuery } from '../queries';

const mockRenownQuery = vi.mocked(usePersonaRenownQuery);
const mockShipsQuery = vi.mocked(useMyShipsQuery);

function makeRenown(overrides: Partial<RenownPayload> = {}): RenownPayload {
  return {
    persona_id: 1,
    persona_name: 'Alice',
    prestige: { dwellings: 0, items: 0, orgs: 0, deeds: 0, fashion: 0, total: 0 },
    fame: {
      points: 0,
      tier: 'unknown',
      tier_label: 'Unknown',
      tier_multiplier: 1,
      next_tier: null,
      next_tier_threshold: null,
    },
    reputation: [],
    recent_deeds: [],
    owned_dwellings: [],
    tenanted_rooms: [],
    ...overrides,
  } as RenownPayload;
}

function setRenown(payload: RenownPayload | undefined, isLoading = false) {
  mockRenownQuery.mockReturnValue({
    data: payload,
    isLoading,
  } as unknown as UseQueryResult<RenownPayload, Error>);
}

function setShips(ships: MyShip[] | undefined, isLoading = false) {
  mockShipsQuery.mockReturnValue({
    data: ships,
    isLoading,
  } as unknown as UseQueryResult<MyShip[], Error>);
}

describe('LocationsTab', () => {
  it('renders dwelling, room, and ship names under their section headings', () => {
    setRenown(
      makeRenown({
        owned_dwellings: [
          {
            id: 1,
            name: 'The Rookery',
            polish_by_category: [],
            upkeep_warning: false,
            decayed_features_count: 0,
            dormant: false,
            dormant_since: null,
          },
        ],
        tenanted_rooms: [{ id: 2, name: 'Garret Room', polish_by_category: [] }],
      })
    );
    setShips([
      {
        id: 3,
        ship_type: {
          id: 1,
          name: 'The Gull',
          description: '',
          base_hull: 10,
          base_handling: 10,
          base_armament: 10,
          base_crew_capacity: 4,
          base_cargo_capacity: 4,
        },
        effective_handling: 10,
        effective_armament: 10,
        effective_hull: 10,
        handling_level: 0,
        armament_level: 0,
        crew_capacity: 4,
        cargo_capacity: 4,
        needs_repair: false,
        owner_persona_id: 1,
        owner_persona_name: 'Alice',
        owner_covenant_id: null,
        owner_covenant_name: null,
      },
    ]);

    renderWithProviders(<LocationsTab personaId={1} isActiveCharacter />);

    expect(screen.getByText('Owned Dwellings')).toBeInTheDocument();
    expect(screen.getByText('The Rookery')).toBeInTheDocument();
    expect(screen.getByText('Tenanted Rooms')).toBeInTheDocument();
    expect(screen.getByText('Garret Room')).toBeInTheDocument();
    expect(screen.getByText('Ships')).toBeInTheDocument();
    expect(screen.getByText('The Gull')).toBeInTheDocument();
  });

  it('renders the Domains placeholder line', () => {
    setRenown(makeRenown());
    setShips([]);

    renderWithProviders(<LocationsTab personaId={1} isActiveCharacter />);

    expect(screen.getByTestId('domains-placeholder')).toHaveTextContent(
      'Domains your organizations hold will appear here (#1884).'
    );
  });

  it('shows a muted message when there is no active persona to view', () => {
    setRenown(undefined);
    setShips(undefined);

    renderWithProviders(<LocationsTab personaId={null} isActiveCharacter />);

    expect(screen.getByText(/No active character to view locations for/i)).toBeInTheDocument();
  });

  it('shows a muted notice instead of ships when viewing a non-active character', () => {
    setRenown(
      makeRenown({
        owned_dwellings: [],
        tenanted_rooms: [],
      })
    );
    setShips([
      {
        id: 3,
        ship_type: {
          id: 1,
          name: 'The Gull',
          description: '',
          base_hull: 10,
          base_handling: 10,
          base_armament: 10,
          base_crew_capacity: 4,
          base_cargo_capacity: 4,
        },
        effective_handling: 10,
        effective_armament: 10,
        effective_hull: 10,
        handling_level: 0,
        armament_level: 0,
        crew_capacity: 4,
        cargo_capacity: 4,
        needs_repair: false,
        owner_persona_id: 1,
        owner_persona_name: 'Alice',
        owner_covenant_id: null,
        owner_covenant_name: null,
      },
    ]);

    renderWithProviders(<LocationsTab personaId={1} isActiveCharacter={false} />);

    expect(screen.getByText('Ships are visible while playing this character.')).toBeInTheDocument();
    expect(screen.queryByText('The Gull')).not.toBeInTheDocument();
    expect(screen.queryByText('Ships')).not.toBeInTheDocument();
  });
});
