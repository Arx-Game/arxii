import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderAreaManager, WorldBuilderRoom } from '../../types';
import { CategoryDoorDialog } from '../CategoryDoorDialog';

// The sections carry their own focused coverage (and their own detail
// queries); thin mocks keep this file to the door-routing contract.
vi.mock('../../components/RoomAuthoringSections', () => ({
  AtmosphereSection: () => <div data-testid="mock-atmosphere-section" />,
  StaffingSection: () => <div data-testid="mock-staffing-section" />,
  PlacesSection: () => <div data-testid="mock-places-section" />,
  FeatureSection: () => <div data-testid="mock-feature-section" />,
  StatsSection: () => <div data-testid="mock-stats-section" />,
}));
vi.mock('../../components/PlaceClueDialog', () => ({
  PlaceClueDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="mock-place-clue-dialog" /> : null,
}));

const catalogs: WorldBuilderAreaManager['catalogs'] = {
  species: [],
  resonances: [],
  distinctions: [],
  fame_tiers: [],
  realms: [],
  climates: [],
  societies: [],
  permit_options: [],
  feature_kinds: [],
  npc_roles: [],
  blueprints: [],
  size_tiers: [],
  starting_areas: [],
  beginnings: [],
};

function makeRoom(overrides: Partial<WorldBuilderRoom> = {}): WorldBuilderRoom {
  return {
    id: 100,
    name: 'The Grand Foyer',
    description: '',
    is_public: true,
    is_social_hub: false,
    is_outdoor: false,
    enclosure: 'walled',
    size_name: null,
    grid_x: 0,
    grid_y: 0,
    floor: 0,
    fixture_key: null,
    origin: 'authored',
    exported_at: null,
    published_at: null,
    needs_prose: false,
    art_url: null,
    stats: [],
    area_id: 5,
    size_units: null,
    default_blueprint: null,
    places: [],
    feature: null,
    functionaries: [],
    ambient_counts: { lines: 0, emits: 0 },
    travel_hub: null,
    starting_bindings: [],
    occupant_count: 0,
    clues: [],
    clue_triggers: [],
    portal_anchors: [],
    desc_variants: [],
    ...overrides,
  };
}

describe('CategoryDoorDialog', () => {
  it.each([
    ['ambience', 'mock-atmosphere-section'],
    ['people', 'mock-staffing-section'],
    ['law', 'mock-stats-section'],
  ] as const)('the %s door reveals its reused Phase B editor', (door, sectionTestId) => {
    renderWithProviders(
      <CategoryDoorDialog
        door={door}
        onClose={vi.fn()}
        room={makeRoom()}
        catalogs={catalogs}
        runAction={vi.fn()}
      />
    );
    expect(screen.getByTestId(sectionTestId)).toBeInTheDocument();
  });

  it('the places door reveals both Places and Feature editors', () => {
    renderWithProviders(
      <CategoryDoorDialog
        door="places"
        onClose={vi.fn()}
        room={makeRoom()}
        catalogs={catalogs}
        runAction={vi.fn()}
      />
    );
    expect(screen.getByTestId('mock-places-section')).toBeInTheDocument();
    expect(screen.getByTestId('mock-feature-section')).toBeInTheDocument();
  });

  it('the secrets door lists placements with removes and opens PlaceClueDialog', async () => {
    const runAction = vi.fn();
    renderWithProviders(
      <CategoryDoorDialog
        door="secrets"
        onClose={vi.fn()}
        room={makeRoom({
          clues: [
            {
              id: 11,
              clue_name: 'The Bloodied Ledger',
              clue_slug: 'bloodied-ledger',
              detect_difficulty: 30,
              fixture_key: null,
            },
          ],
          clue_triggers: [
            {
              id: 12,
              clue_name: 'A Familiar Crest',
              clue_slug: 'familiar-crest',
              fixture_key: null,
            },
          ],
        })}
        catalogs={catalogs}
        runAction={runAction}
      />
    );

    await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
    expect(runAction).toHaveBeenCalledWith('staff_remove_clue', { room_clue_id: 11 });

    await userEvent.click(screen.getByTestId('secrets-place-clue'));
    expect(screen.getByTestId('mock-place-clue-dialog')).toBeInTheDocument();
  });
});
