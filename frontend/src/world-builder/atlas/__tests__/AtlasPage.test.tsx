import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type {
  WorldBuilderArea,
  WorldBuilderAreaManager,
  WorldBuilderRoomDetail,
  WorldBuilderRoomHit,
} from '../../types';
import { AtlasPage } from '../AtlasPage';

vi.mock('../../queries', () => ({
  useWorldBuilderAreasQuery: vi.fn(),
  useMyGrantsQuery: vi.fn(),
  useAreaManagerQuery: vi.fn(),
  useRoomDetailQuery: vi.fn(),
  useRoomSearchQuery: vi.fn(),
  useWorldBuilderAction: vi.fn(() => ({ mutateAsync: vi.fn() })),
}));

vi.mock('../../useWorldBuilderActor', () => ({
  useWorldBuilderActor: () => 7,
}));

// Radix Select has no jsdom-friendly interaction; the insert dialog's level
// pick is preselected, so a plain <select> stand-in keeps the dialog renderable.
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
  }) => (
    <select
      value={value}
      onChange={(event) => onValueChange?.(event.target.value)}
      aria-label="level picker"
    >
      <option value="" disabled></option>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('../AreaPage', () => ({
  AreaPage: ({
    areaId,
    onDescend,
    onOpenAreaDoc,
    highlightRoomId,
  }: {
    areaId: number;
    onDescend: (next: { kind: string; id: number }) => void;
    onOpenAreaDoc: (id: number) => void;
    highlightRoomId?: number | null;
  }) => (
    <div
      data-testid="mock-area-page"
      data-area-id={areaId}
      data-highlight-room-id={highlightRoomId ?? ''}
    >
      <button onClick={() => onDescend({ kind: 'roomdoc', id: 999 })}>descend</button>
      <button onClick={() => onOpenAreaDoc(areaId)}>edit</button>
    </div>
  ),
}));

vi.mock('../../document/RoomDocument', () => ({
  RoomDocument: ({ roomId }: { roomId: number }) => (
    <div data-testid="mock-room-document" data-room-id={roomId} />
  ),
}));

vi.mock('../../document/AreaDocument', () => ({
  AreaDocument: ({
    areaId,
    onDeleted,
  }: {
    areaId: number;
    onDeleted: (parentAreaId: number | null) => void;
  }) => (
    <div data-testid="mock-area-document" data-area-id={areaId}>
      <button onClick={() => onDeleted(1)}>deleted-with-parent</button>
      <button onClick={() => onDeleted(null)}>deleted-root</button>
    </div>
  ),
}));

vi.mock('../IndexRail', () => ({
  IndexRail: ({ current }: { current: { kind: string; id: number } | null }) => (
    <div data-testid="mock-index-rail">{current ? `${current.kind}:${current.id}` : 'none'}</div>
  ),
}));

const {
  useWorldBuilderAreasQuery,
  useAreaManagerQuery,
  useRoomDetailQuery,
  useRoomSearchQuery,
  useMyGrantsQuery,
  useWorldBuilderAction,
} = await import('../../queries');

/** A dispatch stand-in that answers `create_area` and `staff_dig_room` with ids, everything else plainly. */
function mockDispatch() {
  const mutateAsync = vi.fn(async ({ key }: { key: string }) => {
    if (key === 'create_area') return { success: true, message: '', data: { area_id: 77 } };
    return { success: true, message: '' };
  });
  vi.mocked(useWorldBuilderAction).mockReturnValue({ mutateAsync } as never);
  return mutateAsync;
}

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
    breadcrumb: [
      { id: 1, name: 'Nitera', level: 80, level_display: 'World', grid_x: null, grid_y: null },
      {
        id: area.id,
        name: area.name,
        level: area.level,
        level_display: area.level_display,
        grid_x: area.grid_x,
        grid_y: area.grid_y,
      },
    ],
    rooms: [],
    resonances: [],
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
  vi.mocked(useRoomDetailQuery).mockReturnValue({ data: undefined, isLoading: false } as never);
  vi.mocked(useMyGrantsQuery).mockReturnValue({ data: { is_staff: true, grants: [] } } as never);
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

  it('a granted GM roots at their warrant, not the world (#3534)', async () => {
    mockQueries({ 5: makeManager(centralWard) });
    vi.mocked(useMyGrantsQuery).mockReturnValue({
      data: {
        is_staff: false,
        grants: [
          {
            area_id: 5,
            area_name: 'Central Ward',
            area_level: 30,
            max_level: 10,
            room_budget: 8,
            rooms_used: 3,
          },
        ],
      },
    } as never);

    renderWithProviders(<AtlasPage />);

    expect(await screen.findByTestId('mock-area-page')).toHaveAttribute('data-area-id', '5');
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

  it('inserts a level between two crumb entries: create it at the lower spot, re-parent the lower area', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    const placedWard = makeArea({
      id: 5,
      name: 'Central Ward',
      level: 30,
      parent: 1,
      grid_x: 2,
      grid_y: 3,
    });
    mockQueries({ 5: makeManager(placedWard), 1: makeManager(nitera) });
    const mutateAsync = mockDispatch();

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByTestId('folio-crumb-insert'));
    // World ❯ Ward: the highest fitting level (Continent) is preselected.
    expect(screen.getByLabelText('Continent name')).toBeInTheDocument();
    await userEvent.type(screen.getByTestId('insert-level-name'), 'Catenys');
    await userEvent.click(screen.getByTestId('insert-level-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync.mock.calls.map(([input]) => input)).toEqual([
      {
        key: 'create_area',
        kwargs: { name: 'Catenys', slug: 'catenys', level: 70, parent_id: 1, grid_x: 2, grid_y: 3 },
      },
      { key: 'edit_area', kwargs: { area_id: 5, parent_id: 77, grid_x: 0, grid_y: 0 } },
    ]);
  });

  it('inserting above a room moves the room inside the new level and places it at the origin', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'roomdoc', id: 100 })
    );
    mockQueries({ 1: makeManager(nitera) });
    vi.mocked(useRoomDetailQuery).mockReturnValue({
      data: {
        id: 100,
        room: { id: 100, name: 'The City Center', grid_x: 4, grid_y: 5, floor: 0 },
        breadcrumb: [
          { id: 2, name: 'Arx City', level: 40, level_display: 'City', grid_x: null, grid_y: null },
        ],
        exits: [],
      } as unknown as WorldBuilderRoomDetail,
      isLoading: false,
    } as never);
    const mutateAsync = mockDispatch();

    renderWithProviders(<AtlasPage />);
    expect(screen.getByTestId('folio-crumb-current')).toHaveTextContent('The City Center');
    await userEvent.click(screen.getByTestId('folio-crumb-insert'));
    expect(screen.getByLabelText('Ward name')).toBeInTheDocument();
    await userEvent.type(screen.getByTestId('insert-level-name'), 'Central Ward');
    await userEvent.click(screen.getByTestId('insert-level-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
    expect(mutateAsync.mock.calls.map(([input]) => input)).toEqual([
      {
        key: 'create_area',
        kwargs: {
          name: 'Central Ward',
          slug: 'central-ward',
          level: 30,
          parent_id: 2,
          grid_x: 4,
          grid_y: 5,
        },
      },
      { key: 'staff_move_room', kwargs: { room_id: 100, area_id: 77 } },
      { key: 'staff_place_room', kwargs: { room_id: 100, grid_x: 0, grid_y: 0, floor: 0 } },
    ]);
  });

  it('a refused create leaves the lower node where it was', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard), 1: makeManager(nitera) });
    const mutateAsync = vi.fn(async () => ({ success: false, message: 'refused' }));
    vi.mocked(useWorldBuilderAction).mockReturnValue({ mutateAsync } as never);

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByTestId('folio-crumb-insert'));
    await userEvent.type(screen.getByTestId('insert-level-name'), 'Catenys');
    await userEvent.click(screen.getByTestId('insert-level-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).not.toHaveBeenCalledWith(expect.objectContaining({ key: 'edit_area' }));
  });

  it("opens the area document from AreaPage's ✎ Edit", async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('edit'));

    expect(await screen.findByTestId('mock-area-document')).toHaveAttribute('data-area-id', '5');
  });

  it("a deleted area's document lands on the parent's page", async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'areadoc', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard), 1: makeManager(nitera) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('deleted-with-parent'));

    expect(await screen.findByTestId('mock-area-page')).toHaveAttribute('data-area-id', '1');
  });

  it('a deleted ROOT area falls back to the first root', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'areadoc', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard), 1: makeManager(nitera) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('deleted-root'));

    expect(await screen.findByTestId('mock-area-page')).toHaveAttribute('data-area-id', '1');
  });

  it('descends into the room document from AreaPage', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) });

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByText('descend'));

    expect(await screen.findByTestId('mock-room-document')).toHaveAttribute('data-room-id', '999');
  });

  it('a search hit lands on its PARENT grid, highlighted — not straight into the room document', async () => {
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
    // Live filtering: the search hook is re-invoked with each typed term, not
    // just called once on dialog open.
    expect(useRoomSearchQuery).toHaveBeenCalledWith('kit');

    await userEvent.click(await screen.findByTestId('room-search-hit'));

    const areaPage = await screen.findByTestId('mock-area-page');
    expect(areaPage).toHaveAttribute('data-area-id', '5');
    expect(areaPage).toHaveAttribute('data-highlight-room-id', '42');
    expect(screen.queryByTestId('mock-room-document')).not.toBeInTheDocument();
  });

  it('a hit with no area falls back to opening its document directly', async () => {
    window.localStorage.setItem(
      'world-builder-atlas:anon:last-location',
      JSON.stringify({ kind: 'area', id: 5 })
    );
    mockQueries({ 5: makeManager(centralWard) }, [
      { id: 43, name: 'Orphan Room', area_id: null, area_name: null, floor: 0, fixture_key: null },
    ]);

    renderWithProviders(<AtlasPage />);
    await userEvent.click(screen.getByTestId('open-room-search'));
    await userEvent.type(screen.getByTestId('room-search-input'), 'orph');
    await userEvent.click(await screen.findByTestId('room-search-hit'));

    expect(await screen.findByTestId('mock-room-document')).toHaveAttribute('data-room-id', '43');
  });
});
