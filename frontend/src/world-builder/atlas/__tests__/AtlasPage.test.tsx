import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea, WorldBuilderAreaManager, WorldBuilderRoomHit } from '../../types';
import { AtlasPage } from '../AtlasPage';

vi.mock('../../queries', () => ({
  useWorldBuilderAreasQuery: vi.fn(),
  useAreaManagerQuery: vi.fn(),
  useRoomSearchQuery: vi.fn(),
}));

vi.mock('../AreaPage', () => ({
  AreaPage: ({
    areaId,
    onDescend,
    onOpenAreaDoc,
  }: {
    areaId: number;
    onDescend: (next: { kind: string; id: number }) => void;
    onOpenAreaDoc: (id: number) => void;
  }) => (
    <div data-testid="mock-area-page" data-area-id={areaId}>
      <button onClick={() => onDescend({ kind: 'roomdoc', id: 999 })}>descend</button>
      <button onClick={() => onOpenAreaDoc(areaId)}>edit</button>
    </div>
  ),
}));

vi.mock('../IndexRail', () => ({
  IndexRail: ({ current }: { current: { kind: string; id: number } | null }) => (
    <div data-testid="mock-index-rail">{current ? `${current.kind}:${current.id}` : 'none'}</div>
  ),
}));

const { useWorldBuilderAreasQuery, useAreaManagerQuery, useRoomSearchQuery } = await import(
  '../../queries'
);

function makeArea(overrides: Partial<WorldBuilderArea> = {}): WorldBuilderArea {
  return {
    id: 1,
    name: 'Nitera',
    slug: null,
    level: 80,
    level_display: 'World',
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

function makeManager(area: WorldBuilderArea): WorldBuilderAreaManager {
  return {
    area,
    catalogs: {
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
    breadcrumb: [
      { id: 1, name: 'Nitera', level_display: 'World' },
      { id: area.id, name: area.name, level_display: area.level_display },
    ],
    rooms: [],
    exits: [],
  };
}

const nitera = makeArea({ id: 1, name: 'Nitera', level: 80 });
const centralWard = makeArea({ id: 5, name: 'Central Ward', level: 30, parent: 1 });

function mockQueries(
  areaManagers: Record<number, WorldBuilderAreaManager>,
  hits: WorldBuilderRoomHit[] = []
) {
  vi.mocked(useWorldBuilderAreasQuery).mockImplementation((params = {}) => {
    if (params.hasParent === false) {
      return { data: { results: [nitera], count: 1 }, isLoading: false } as never;
    }
    return { data: { results: [], count: 0 }, isLoading: false } as never;
  });
  vi.mocked(useAreaManagerQuery).mockImplementation((areaId) => {
    if (areaId == null) return { data: undefined, isLoading: false } as never;
    return { data: areaManagers[areaId], isLoading: false } as never;
  });
  vi.mocked(useRoomSearchQuery).mockReturnValue({ data: hits, isLoading: false } as never);
}

describe('AtlasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('restores the last location from localStorage instead of the default root', () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) });

    renderWithProviders(<AtlasPage />);

    expect(screen.getByTestId('mock-area-page')).toHaveAttribute('data-area-id', '5');
  });

  it('defaults to the first root area when nothing is stored', async () => {
    mockQueries({ 1: makeManager(nitera) });

    renderWithProviders(<AtlasPage />);

    expect(await screen.findByTestId('mock-area-page')).toHaveAttribute('data-area-id', '1');
  });

  it("renders the folio crumb from the current area's breadcrumb, ancestors clickable", async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard), 1: makeManager(nitera) });

    renderWithProviders(<AtlasPage />);

    expect(screen.getByTestId('folio-crumb-current')).toHaveTextContent('Central Ward');
    await userEvent.click(screen.getByText('Nitera'));

    expect(await screen.findByTestId('mock-area-page')).toHaveAttribute('data-area-id', '1');
  });

  it("opens the areadoc placeholder from AreaPage's ✎ Edit", async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('edit'));

    expect(await screen.findByTestId('areadoc-placeholder')).toBeInTheDocument();
  });

  it('descends into a roomdoc placeholder from AreaPage', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('descend'));

    expect(await screen.findByTestId('roomdoc-placeholder')).toBeInTheDocument();
  });

  it('opens the room search dialog and navigates to a hit', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) }, [
      {
        id: 42,
        name: 'Kitchen',
        area_id: 5,
        area_name: 'Central Ward',
        floor: 0,
        fixture_key: null,
      },
    ]);

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByTestId('open-room-search'));
    expect(screen.getByText('Find a room')).toBeInTheDocument();

    await userEvent.type(screen.getByTestId('room-search-input'), 'kit');
    await userEvent.click(await screen.findByTestId('room-search-hit'));

    expect(await screen.findByTestId('roomdoc-placeholder')).toBeInTheDocument();
  });
});
