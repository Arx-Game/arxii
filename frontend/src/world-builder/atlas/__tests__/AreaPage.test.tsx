import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea, WorldBuilderAreaManager, WorldBuilderRoom } from '../../types';
import { AreaPage } from '../AreaPage';
import type { LatticeProps } from '../Lattice';

vi.mock('../../queries', () => ({
  useAreaManagerQuery: vi.fn(),
  useWorldBuilderAreasQuery: vi.fn(),
  useWorldBuilderAction: vi.fn(() => ({ mutate: vi.fn() })),
}));

vi.mock('../../useWorldBuilderActor', () => ({
  useWorldBuilderActor: () => 1,
}));

// AreaPage's own tests care about which tiles/mode it hands the Lattice, not
// the Lattice's own gesture mechanics (that's Lattice.test.tsx's job) — a
// thin stub keeps this file a unit test of AreaPage's wiring only.
vi.mock('../Lattice', () => ({
  Lattice: ({ mode, tiles, onOpen, highlightTileId }: LatticeProps) => (
    <div data-testid="lattice-mock" data-mode={mode} data-highlight-tile-id={highlightTileId ?? ''}>
      {tiles.map((tile) => (
        <button key={tile.id} data-testid={`mock-tile-${tile.id}`} onClick={() => onOpen(tile)}>
          {tile.name}
        </button>
      ))}
    </div>
  ),
}));

const { useAreaManagerQuery, useWorldBuilderAreasQuery } = await import('../../queries');

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
    id: 100,
    name: 'City Center',
    description: '',
    is_public: true,
    is_social_hub: false,
    is_outdoor: true,
    enclosure: 'open_air',
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
    area_id: 1,
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
const cityCenter = makeRoom({ id: 100, name: 'City Center', area_id: 1, published_at: null });
const foyerUnpublishedRoom = makeRoom({
  id: 200,
  name: 'Gallery Stair',
  area_id: 2,
  published_at: null,
});
const foyerPublishedRoom = makeRoom({
  id: 201,
  name: 'Fountain Court',
  area_id: 2,
  published_at: '2026-01-01T00:00:00Z',
});

function mockQueries({
  areaManagers,
  wardChildren,
}: {
  areaManagers: Record<number, WorldBuilderAreaManager | undefined>;
  wardChildren: WorldBuilderArea[];
}) {
  vi.mocked(useAreaManagerQuery).mockImplementation((areaId) => {
    if (areaId == null) return { data: undefined, isLoading: false } as never;
    return { data: areaManagers[areaId], isLoading: false } as never;
  });
  vi.mocked(useWorldBuilderAreasQuery).mockImplementation((params = {}, enabled) => {
    if (params.parent === 1 && enabled !== false) {
      return {
        data: { results: wardChildren, count: wardChildren.length },
        isLoading: false,
      } as never;
    }
    return { data: { results: [], count: 0 }, isLoading: false } as never;
  });
}

describe('AreaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children (sub-areas and direct rooms) as ledger rows, and both as Lattice tiles', () => {
    mockQueries({
      areaManagers: { 1: makeManager(ward, [cityCenter]) },
      wardChildren: [foyer],
    });

    renderWithProviders(<AreaPage areaId={1} onDescend={vi.fn()} onOpenAreaDoc={vi.fn()} />);

    const rows = screen.getAllByTestId('ledger-area-row');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('The Grand Foyer');

    const roomRows = screen.getAllByTestId('ledger-room-row');
    expect(roomRows).toHaveLength(1);
    expect(roomRows[0]).toHaveTextContent('City Center');
    expect(roomRows[0]).toHaveTextContent('unpublished');

    expect(screen.getByTestId('lattice-mock')).toHaveAttribute('data-mode', 'areas');
    expect(screen.getByTestId('mock-tile-2')).toHaveTextContent('The Grand Foyer');
    expect(screen.getByTestId('mock-tile-100')).toHaveTextContent('City Center');
  });

  it('descends into a child area on click', async () => {
    mockQueries({ areaManagers: { 1: makeManager(ward, []) }, wardChildren: [foyer] });
    const onDescend = vi.fn();

    renderWithProviders(<AreaPage areaId={1} onDescend={onDescend} onOpenAreaDoc={vi.fn()} />);
    await userEvent.click(screen.getByTestId('ledger-area-row'));

    expect(onDescend).toHaveBeenCalledWith({ kind: 'roomgrid', id: 2 });
  });

  it('opens a direct room as a room document on click', async () => {
    mockQueries({ areaManagers: { 1: makeManager(ward, [cityCenter]) }, wardChildren: [] });
    const onDescend = vi.fn();

    renderWithProviders(<AreaPage areaId={1} onDescend={onDescend} onOpenAreaDoc={vi.fn()} />);
    await userEvent.click(screen.getByTestId('ledger-room-row'));

    expect(onDescend).toHaveBeenCalledWith({ kind: 'roomdoc', id: 100 });
  });

  it("shows a BUILDING child's own room total alongside its unpublished count", () => {
    mockQueries({
      areaManagers: {
        1: makeManager(ward, []),
        2: makeManager(foyer, [foyerUnpublishedRoom, foyerPublishedRoom]),
      },
      wardChildren: [foyer],
    });

    renderWithProviders(<AreaPage areaId={1} onDescend={vi.fn()} onOpenAreaDoc={vi.fn()} />);
    const row = screen.getByTestId('ledger-area-row');
    expect(row).toHaveTextContent('1 unpublished');
    expect(screen.getByTestId('ledger-area-kind')).toHaveTextContent('2 rooms');
  });

  it('calls onOpenAreaDoc from the ✎ Edit affordance', async () => {
    mockQueries({ areaManagers: { 1: makeManager(ward, []) }, wardChildren: [] });
    const onOpenAreaDoc = vi.fn();

    renderWithProviders(<AreaPage areaId={1} onDescend={vi.fn()} onOpenAreaDoc={onOpenAreaDoc} />);
    await userEvent.click(screen.getByText('✎ Edit'));

    expect(onOpenAreaDoc).toHaveBeenCalledWith(1);
  });

  it('skips the ledger entirely for a BUILDING-level area — rooms belong to the lattice', () => {
    mockQueries({
      areaManagers: { 2: makeManager(foyer, [foyerUnpublishedRoom]) },
      wardChildren: [],
    });

    renderWithProviders(<AreaPage areaId={2} onDescend={vi.fn()} onOpenAreaDoc={vi.fn()} />);

    expect(screen.queryByTestId('area-ledger')).not.toBeInTheDocument();
    expect(screen.getByTestId('lattice-mock')).toHaveAttribute('data-mode', 'rooms');
    expect(screen.getByTestId('mock-tile-200')).toHaveTextContent('Gallery Stair');
  });

  it('opens a Lattice room tile as a room document', async () => {
    mockQueries({
      areaManagers: { 2: makeManager(foyer, [foyerUnpublishedRoom]) },
      wardChildren: [],
    });
    const onDescend = vi.fn();

    renderWithProviders(<AreaPage areaId={2} onDescend={onDescend} onOpenAreaDoc={vi.fn()} />);
    await userEvent.click(screen.getByTestId('mock-tile-200'));

    expect(onDescend).toHaveBeenCalledWith({ kind: 'roomdoc', id: 200 });
  });

  it('passes highlightRoomId through to the Lattice as highlightTileId', () => {
    mockQueries({ areaManagers: { 1: makeManager(ward, [cityCenter]) }, wardChildren: [] });

    renderWithProviders(
      <AreaPage areaId={1} onDescend={vi.fn()} onOpenAreaDoc={vi.fn()} highlightRoomId={100} />
    );

    expect(screen.getByTestId('lattice-mock')).toHaveAttribute('data-highlight-tile-id', '100');
  });

  it('opens a Lattice area tile at its own level', async () => {
    mockQueries({
      areaManagers: { 1: makeManager(ward, []) },
      wardChildren: [foyer],
    });
    const onDescend = vi.fn();

    renderWithProviders(<AreaPage areaId={1} onDescend={onDescend} onOpenAreaDoc={vi.fn()} />);
    await userEvent.click(screen.getByTestId('mock-tile-2'));

    expect(onDescend).toHaveBeenCalledWith({ kind: 'roomgrid', id: 2 });
  });
});
