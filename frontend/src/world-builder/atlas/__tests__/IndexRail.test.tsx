import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea, WorldBuilderAreaManager, WorldBuilderRoom } from '../../types';
import { IndexRail } from '../IndexRail';

interface MockAccount {
  is_staff?: boolean;
  is_gm?: boolean;
}

let mockAccount: MockAccount | null = null;

vi.mock('@/store/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/hooks')>();
  return {
    ...actual,
    useAccount: () => mockAccount,
  };
});

vi.mock('../../queries', () => ({
  useWorldBuilderAreasQuery: vi.fn(),
  useAreaManagerQuery: vi.fn(),
}));

const { useWorldBuilderAreasQuery, useAreaManagerQuery } = await import('../../queries');

function makeArea(overrides: Partial<WorldBuilderArea> = {}): WorldBuilderArea {
  return {
    id: 1,
    name: 'Central Ward',
    slug: null,
    level: 30,
    level_display: 'Ward',
    origin: 'authored',
    parent: null,
    children_count: 1,
    grid_x: null,
    grid_y: null,
    realm: null,
    climate: null,
    dominant_society: null,
    effective_climate: null,
    art_url: null,
    description: '',
    color: '',
    permit_eligibility: 'open' as const,
    ...overrides,
  };
}

function makeRoom(overrides: Partial<WorldBuilderRoom> = {}): WorldBuilderRoom {
  return {
    id: 200,
    name: 'Gallery Stair',
    description: '',
    is_public: true,
    is_social_hub: false,
    is_outdoor: false,
    enclosure: 'roofed',
    size_name: null,
    grid_x: null,
    grid_y: null,
    floor: 0,
    fixture_key: null,
    origin: 'authored',
    exported_at: null,
    published_at: null,
    needs_prose: false,
    art_url: null,
    stats: [],
    area_id: 2,
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

function makeManager(
  area: WorldBuilderArea,
  rooms: WorldBuilderRoom[] = []
): WorldBuilderAreaManager {
  return {
    area,
    catalogs: {
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
    },
    breadcrumb: [{ id: area.id, name: area.name, level_display: area.level_display }],
    rooms,
    resonances: [],
    exits: [],
  };
}

const ward = makeArea({ id: 1, name: 'Central Ward', level: 30, children_count: 1 });
const foyer = makeArea({ id: 2, name: 'The Grand Foyer', level: 10, parent: 1, children_count: 0 });
const unpublishedRoom = makeRoom({
  id: 200,
  name: 'Gallery Stair',
  area_id: 2,
  published_at: null,
});
const publishedRoom = makeRoom({
  id: 201,
  name: 'Fountain Court',
  area_id: 2,
  published_at: '2026-01-01T00:00:00Z',
});

function mockQueries() {
  vi.mocked(useWorldBuilderAreasQuery).mockImplementation((params = {}, enabled) => {
    if (params.hasParent === false) {
      return { data: { results: [ward], count: 1 }, isLoading: false } as never;
    }
    if (params.parent === 1 && enabled !== false) {
      return { data: { results: [foyer], count: 1 }, isLoading: false } as never;
    }
    return { data: { results: [], count: 0 }, isLoading: false } as never;
  });
  vi.mocked(useAreaManagerQuery).mockImplementation((areaId) => {
    if (areaId === 2) {
      return {
        data: makeManager(foyer, [unpublishedRoom, publishedRoom]),
        isLoading: false,
      } as never;
    }
    if (areaId === 1) {
      return { data: makeManager(ward, [unpublishedRoom]), isLoading: false } as never;
    }
    return { data: undefined, isLoading: false } as never;
  });
}

describe('IndexRail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccount = { is_staff: true, is_gm: false };
    mockQueries();
  });

  it('renders the warrant-scoped tree, expanding a building to show unpublished rooms', async () => {
    renderWithProviders(<IndexRail current={null} onSelect={vi.fn()} pinned={[]} recents={[]} />);

    expect(screen.getByText('Central Ward')).toBeInTheDocument();
    expect(screen.getByTestId('index-scope')).toHaveTextContent('Staff warrant');

    await userEvent.click(screen.getByTestId('index-expand-1'));
    expect(await screen.findByText('The Grand Foyer')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('index-expand-2'));
    const galleryStair = await screen.findByText('Gallery Stair');
    expect(galleryStair.closest('[data-testid="index-room-node"]')).toHaveTextContent(
      'unpublished'
    );

    const fountainCourt = screen.getByText('Fountain Court');
    expect(fountainCourt.closest('[data-testid="index-room-node"]')).not.toHaveTextContent(
      'unpublished'
    );
  });

  it('shows GM-scoped copy for a non-staff GM account', () => {
    mockAccount = { is_staff: false, is_gm: true };
    renderWithProviders(<IndexRail current={null} onSelect={vi.fn()} pinned={[]} recents={[]} />);
    expect(screen.getByTestId('index-scope')).toHaveTextContent('granted');
  });

  it('selects an area node', async () => {
    const onSelect = vi.fn();
    renderWithProviders(<IndexRail current={null} onSelect={onSelect} pinned={[]} recents={[]} />);

    await userEvent.click(screen.getByTestId('index-area-node'));
    expect(onSelect).toHaveBeenCalledWith({ kind: 'area', id: 1 }, 'Central Ward');
  });

  it("jumps to a room from the current area's unpublished list", async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <IndexRail current={{ kind: 'area', id: 1 }} onSelect={onSelect} pinned={[]} recents={[]} />
    );

    expect(screen.getByTestId('index-unpublished')).toHaveTextContent('Unpublished rooms — 1');
    await userEvent.click(screen.getByTestId('index-unpublished-room'));
    expect(onSelect).toHaveBeenCalledWith({ kind: 'roomdoc', id: 200 }, 'Gallery Stair');
  });

  it('renders Pinned and Recent sections, with empty-state copy when there is nothing yet', () => {
    renderWithProviders(<IndexRail current={null} onSelect={vi.fn()} pinned={[]} recents={[]} />);
    expect(screen.getByTestId('index-pinned')).toHaveTextContent('Nothing pinned yet.');
    expect(screen.getByTestId('index-recent')).toHaveTextContent('Nothing visited yet.');
  });

  it('lists pinned and recent entries and navigates on click', async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <IndexRail
        current={null}
        onSelect={onSelect}
        pinned={[{ kind: 'area', id: 1, name: 'Central Ward', visitedAt: '2026-01-01T00:00:00Z' }]}
        recents={[
          { kind: 'roomdoc', id: 200, name: 'Gallery Stair', visitedAt: '2026-01-01T00:00:00Z' },
        ]}
      />
    );

    await userEvent.click(screen.getByTestId('index-pinned').querySelector('button')!);
    expect(onSelect).toHaveBeenCalledWith(
      { kind: 'area', id: 1, name: 'Central Ward', visitedAt: '2026-01-01T00:00:00Z' },
      'Central Ward'
    );
  });

  it('a grant renders its budget as used/total and jumps to the grant area (#3534)', async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <IndexRail
        current={null}
        onSelect={onSelect}
        pinned={[]}
        recents={[]}
        grants={[
          {
            area_id: 5,
            area_name: 'Central Ward',
            area_level: 30,
            max_level: 10,
            room_budget: 8,
            rooms_used: 3,
          },
        ]}
      />
    );

    const block = screen.getByTestId('index-warrant');
    expect(block).toHaveTextContent('3 of 8 rooms');
    await userEvent.click(within(block).getByText('Central Ward'));
    expect(onSelect).toHaveBeenCalledWith({ kind: 'area', id: 5 }, 'Central Ward');
  });
});
