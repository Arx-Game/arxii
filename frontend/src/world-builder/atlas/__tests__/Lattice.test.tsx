import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';

import { Lattice, type LatticeProps, type LatticeTile } from '../Lattice';

// jsdom has no PointerEvent (longstanding gap — https://github.com/jsdom/jsdom/issues/2527),
// so `fireEvent.pointerDown/Move/Up` deliver events with no clientX/clientY at all without
// this. `Lattice`'s drag-to-swap is built on real pointer events, so the drag tests need it.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }
  // @ts-expect-error jsdom doesn't implement PointerEvent
  window.PointerEvent = PointerEventPolyfill;
}

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
    <select value={value} onChange={(event) => onValueChange?.(event.target.value)}>
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

function makeTile(overrides: Partial<LatticeTile> = {}): LatticeTile {
  return {
    id: 1,
    kind: 'room',
    name: 'Test Room',
    kindLabel: 'room',
    unpublished: false,
    gridX: 0,
    gridY: 0,
    floor: 0,
    ...overrides,
  };
}

function renderLattice(props: Partial<LatticeProps> = {}) {
  const runAction = vi.fn();
  const onOpen = vi.fn();
  const fullProps: LatticeProps = {
    mode: 'rooms',
    nodeId: 42,
    tiles: [],
    onOpen,
    runAction,
    ...props,
  };
  const utils = renderWithProviders(<Lattice {...fullProps} />);
  const rerenderWith = (nextProps: Partial<LatticeProps>) => {
    const merged = { ...fullProps, ...nextProps };
    utils.rerender(
      <Provider store={store}>
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <Lattice {...merged} />
          </MemoryRouter>
        </QueryClientProvider>
      </Provider>
    );
  };
  return { ...utils, runAction, onOpen, rerenderWith };
}

/**
 * Drives the pointerdown/move/up sequence a drag needs. jsdom has no layout
 * engine, so `document.elementFromPoint` doesn't exist at all — this stubs
 * it directly (no `vi.spyOn`, which requires the property to already exist).
 */
async function drag(
  fromEl: HTMLElement,
  toEl: HTMLElement | null,
  { distance = 20 }: { distance?: number } = {}
) {
  const original = document.elementFromPoint;
  document.elementFromPoint = () => toEl;
  fireEvent.pointerDown(fromEl, { clientX: 0, clientY: 0, button: 0 });
  fireEvent.pointerMove(window, { clientX: distance, clientY: distance });
  fireEvent.pointerUp(window, { clientX: distance, clientY: distance });
  document.elementFromPoint = original;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('Lattice — plot-then-realize', () => {
  it('renders plottable empty ground when there are no tiles yet', () => {
    renderLattice({ tiles: [] });
    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'empty');
  });

  it('clicking empty ground plans it; clicking the plan opens Add', async () => {
    renderLattice({ tiles: [] });
    const cell = screen.getByTestId('lattice-cell-0-0');

    await userEvent.click(cell);
    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'planned');

    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    expect(screen.getByTestId('add-dialog-name')).toBeInTheDocument();
  });

  it('the ✕ on a planned square unplans it without opening Add', async () => {
    renderLattice({ tiles: [] });
    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    await userEvent.click(screen.getByTestId('lattice-unplan-0-0'));

    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'empty');
    expect(screen.queryByTestId('add-dialog-name')).not.toBeInTheDocument();
  });

  it('right-click carve cycle: plan clears, empty voids, void restores', async () => {
    renderLattice({ tiles: [] });
    const cell = () => screen.getByTestId('lattice-cell-0-0');

    await userEvent.click(cell()); // plan
    fireEvent.contextMenu(cell());
    expect(cell()).toHaveAttribute('data-cell-state', 'empty'); // plan -> clear

    fireEvent.contextMenu(cell());
    expect(cell()).toHaveAttribute('data-cell-state', 'void'); // empty -> void

    fireEvent.contextMenu(cell());
    expect(cell()).toHaveAttribute('data-cell-state', 'empty'); // void -> restore
  });

  it('realized tiles are inert to carving', () => {
    renderLattice({ tiles: [makeTile()] });
    const tile = screen.getByTestId('lattice-tile-1');
    fireEvent.contextMenu(tile);
    // still just the same tile, unaffected — no crash, no state to inspect beyond presence
    expect(screen.getByTestId('lattice-tile-1')).toBeInTheDocument();
  });

  it('rooms mode realize dispatches staff_dig_room at the plotted absolute cell', async () => {
    const { runAction } = renderLattice({ nodeId: 42, tiles: [] });
    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_dig_room', {
      area_id: 42,
      name: 'The Wine Cellar',
      floor: 0,
      grid_x: 1,
      grid_y: 0,
    });
  });

  it('over-ceiling areas mode offers no planning at all (#3534)', async () => {
    renderLattice({ mode: 'areas', tiles: [], childAreaLevel: 20, maxBuildLevel: 10 });
    const cell = screen.getByTestId('lattice-cell-0-0');
    expect(cell).not.toHaveTextContent('⊕');
    await userEvent.click(cell);
    expect(cell).toHaveAttribute('data-cell-state', 'empty');
  });

  it('areas mode realize dispatches create_area with a slugified name and the given level', async () => {
    const { runAction } = renderLattice({
      mode: 'areas',
      nodeId: 7,
      tiles: [],
      childAreaLevel: 10,
    });
    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Grand Foyer');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(runAction).toHaveBeenCalledWith('create_area', {
      name: 'The Grand Foyer',
      slug: 'the-grand-foyer',
      level: 10,
      parent_id: 7,
    });
  });

  it('areas mode hides the connection rows in Add', async () => {
    renderLattice({ mode: 'areas', tiles: [] });
    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    await userEvent.click(screen.getByTestId('lattice-cell-0-0'));
    expect(screen.queryByText(/Entrance from/)).not.toBeInTheDocument();
  });

  it('auto-fills Add from the one adjacent room and resolves the link once the new tile appears', async () => {
    const neighbor = makeTile({ id: 5, name: 'The Gallery Stair', gridX: 0, gridY: 0 });
    const { runAction, rerenderWith } = renderLattice({ nodeId: 42, tiles: [neighbor] });

    // (1,0) is east of the neighbor at (0,0): the neighbor's own exit into
    // the new room is named "east" (Entrance-from); the new room's exit back
    // out to the neighbor is named "west" (Exit-to).
    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    expect(screen.getByTestId('add-dialog-entrance-name')).toHaveValue('east');
    expect(screen.getByTestId('add-dialog-exit-name')).toHaveValue('west');

    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_dig_room', {
      area_id: 42,
      name: 'The Wine Cellar',
      floor: 0,
      grid_x: 1,
      grid_y: 0,
    });
    expect(runAction).not.toHaveBeenCalledWith('staff_link_rooms', expect.anything());

    // The dig "lands": the manager refetch now includes the new room at (1,0).
    const newRoom = makeTile({ id: 99, name: 'The Wine Cellar', gridX: 1, gridY: 0 });
    rerenderWith({ tiles: [neighbor, newRoom] });

    expect(runAction).toHaveBeenCalledWith('staff_link_rooms', {
      room_a_id: 99,
      room_b_id: 5,
      name_ab: 'west',
      name_ba: 'east',
    });
  });

  it('a pending dig-link resolves against the dig floor, not the currently viewed floor', async () => {
    // A pre-existing room sits at (1,0) on floor 1 — the exact cell the
    // floor-0 dig targets. Switching to floor 1 before the refetch lands
    // must NOT hand it the links meant for the dug floor-0 room.
    const neighbor = makeTile({ id: 5, name: 'The Gallery Stair', gridX: 0, gridY: 0, floor: 0 });
    const upstairs = makeTile({ id: 8, name: 'The Loft', gridX: 1, gridY: 0, floor: 1 });
    const { runAction, rerenderWith } = renderLattice({ nodeId: 42, tiles: [neighbor, upstairs] });

    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    await userEvent.click(screen.getByTestId('lattice-cell-1-0'));
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    await userEvent.click(screen.getByTestId('lattice-floor-1'));
    expect(runAction).not.toHaveBeenCalledWith('staff_link_rooms', expect.anything());

    const newRoom = makeTile({ id: 99, name: 'The Wine Cellar', gridX: 1, gridY: 0, floor: 0 });
    rerenderWith({ tiles: [neighbor, upstairs, newRoom] });

    expect(runAction).toHaveBeenCalledWith('staff_link_rooms', {
      room_a_id: 99,
      room_b_id: 5,
      name_ab: 'west',
      name_ba: 'east',
    });
  });

  it('areas mode resolves a pending create_area placement once the unplaced area appears', () => {
    const { runAction, rerenderWith } = renderLattice({
      mode: 'areas',
      nodeId: 7,
      tiles: [],
      childAreaLevel: 10,
    });

    fireEvent.click(screen.getByTestId('lattice-cell-2-1'));
    fireEvent.click(screen.getByTestId('lattice-cell-2-1'));
    fireEvent.change(screen.getByTestId('add-dialog-name'), { target: { value: 'New Ward' } });
    fireEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(runAction).not.toHaveBeenCalledWith('edit_area', expect.anything());

    const unplacedArea = makeTile({
      id: 55,
      kind: 'area',
      name: 'New Ward',
      gridX: null,
      gridY: null,
    });
    rerenderWith({ tiles: [unplacedArea] });

    expect(runAction).toHaveBeenCalledWith('edit_area', { area_id: 55, grid_x: 2, grid_y: 1 });
  });
});

describe('Lattice — drag to arrange', () => {
  it('a completed drag suppresses the click that follows it', async () => {
    const { onOpen } = renderLattice({ tiles: [makeTile({ id: 1 })] });
    const tile = screen.getByTestId('lattice-tile-1');

    await drag(tile, screen.getByTestId('lattice-cell-1-0'));
    fireEvent.click(tile);
    expect(onOpen).not.toHaveBeenCalled();

    // suppression is one-shot: the next ordinary click behaves normally
    fireEvent.click(tile);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  it('a plain click (no movement) opens the tile, not a drag', async () => {
    const { onOpen } = renderLattice({ tiles: [makeTile({ id: 1 })] });
    const tile = screen.getByTestId('lattice-tile-1');

    fireEvent.pointerDown(tile, { clientX: 0, clientY: 0, button: 0 });
    fireEvent.pointerUp(window, { clientX: 0, clientY: 0 });
    fireEvent.click(tile);

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  it('dropping a room tile on open ground repositions it via staff_place_room', async () => {
    const { runAction } = renderLattice({ tiles: [makeTile({ id: 1, floor: 2 })] });
    fireEvent.click(screen.getByTestId('lattice-floor-2'));
    const tile = screen.getByTestId('lattice-tile-1');

    await drag(tile, screen.getByTestId('lattice-cell-1-0'));

    expect(runAction).toHaveBeenCalledWith('staff_place_room', {
      room_id: 1,
      grid_x: 1,
      grid_y: 0,
      floor: 2,
    });
  });

  it('dropping a room tile onto another room tile swaps both positions', async () => {
    const a = makeTile({ id: 1, gridX: 0, gridY: 0 });
    const b = makeTile({ id: 2, name: 'Other Room', gridX: 1, gridY: 0 });
    const { runAction } = renderLattice({ tiles: [a, b] });

    await drag(screen.getByTestId('lattice-tile-1'), screen.getByTestId('lattice-tile-2'));

    expect(runAction).toHaveBeenCalledWith('staff_place_room', {
      room_id: 1,
      grid_x: 1,
      grid_y: 0,
      floor: 0,
    });
    expect(runAction).toHaveBeenCalledWith('staff_place_room', {
      room_id: 2,
      grid_x: 0,
      grid_y: 0,
      floor: 0,
    });
  });

  it('areas mode: dropping a room tile onto an area tile moves it there via staff_move_room', async () => {
    const room = makeTile({ id: 1, kind: 'room', gridX: 0, gridY: 0 });
    const building = makeTile({ id: 2, kind: 'area', name: 'The Grand Foyer', gridX: 1, gridY: 0 });
    const { runAction } = renderLattice({ mode: 'areas', tiles: [room, building] });

    await drag(screen.getByTestId('lattice-tile-1'), screen.getByTestId('lattice-tile-2'));

    expect(runAction).toHaveBeenCalledWith('staff_move_room', { room_id: 1, area_id: 2 });
    expect(runAction).not.toHaveBeenCalledWith('staff_place_room', expect.anything());
  });

  it('dragging an area tile onto a room tile swaps positions via edit_area/staff_place_room (no re-parent)', async () => {
    const building = makeTile({ id: 2, kind: 'area', name: 'The Grand Foyer', gridX: 1, gridY: 0 });
    const room = makeTile({ id: 1, kind: 'room', gridX: 0, gridY: 0 });
    const { runAction } = renderLattice({ mode: 'areas', tiles: [building, room] });

    await drag(screen.getByTestId('lattice-tile-2'), screen.getByTestId('lattice-tile-1'));

    expect(runAction).toHaveBeenCalledWith('edit_area', { area_id: 2, grid_x: 0, grid_y: 0 });
    expect(runAction).toHaveBeenCalledWith('staff_place_room', {
      room_id: 1,
      grid_x: 1,
      grid_y: 0,
      floor: 0,
    });
    expect(runAction).not.toHaveBeenCalledWith('staff_move_room', expect.anything());
  });
});

describe('Lattice — growth', () => {
  it('growing an edge adds ground without moving existing tiles', () => {
    // DEFAULT_BOUNDS already spans y 0..2, so growing north should reach y=3.
    renderLattice({ tiles: [makeTile({ id: 1, gridX: 0, gridY: 0 })] });
    expect(screen.queryByTestId('lattice-cell-0-3')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('lattice-grow-north'));

    expect(screen.getByTestId('lattice-tile-1')).toBeInTheDocument();
    expect(screen.getByTestId('lattice-cell-0-3')).toHaveAttribute('data-cell-state', 'empty');
  });

  it('growing west/south lowers the bound rather than shifting anything', () => {
    renderLattice({ tiles: [makeTile({ id: 1, gridX: 0, gridY: 0 })] });

    fireEvent.click(screen.getByTestId('lattice-grow-west'));
    fireEvent.click(screen.getByTestId('lattice-grow-south'));

    expect(screen.getByTestId('lattice-tile-1')).toBeInTheDocument();
    expect(screen.getByTestId('lattice-cell--1-0')).toBeInTheDocument();
    expect(screen.getByTestId('lattice-cell-0--1')).toBeInTheDocument();
  });
});

describe('Lattice — floors rail (rooms mode only)', () => {
  it('is data-driven from the payload floors, plus ground as a baseline', () => {
    renderLattice({
      tiles: [makeTile({ id: 1, floor: 2 }), makeTile({ id: 2, floor: -1, gridX: 1 })],
    });
    expect(screen.getByTestId('lattice-floor-2')).toBeInTheDocument();
    expect(screen.getByTestId('lattice-floor-0')).toBeInTheDocument();
    expect(screen.getByTestId('lattice-floor--1')).toBeInTheDocument();
  });

  it('is absent in areas mode', () => {
    renderLattice({ mode: 'areas', tiles: [] });
    expect(screen.queryByTestId('lattice-floor-rail')).not.toBeInTheDocument();
  });

  it('⊕ grows a floor at either end and switches to it', () => {
    renderLattice({ tiles: [] });
    fireEvent.click(screen.getByTestId('lattice-floor-grow-up'));
    expect(screen.getByTestId('lattice-floor-1')).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByTestId('lattice-floor-grow-down'));
    expect(screen.getByTestId('lattice-floor--1')).toHaveAttribute('aria-pressed', 'true');
  });

  it('switching floors shows that floor’s own rooms only', () => {
    renderLattice({
      tiles: [
        makeTile({ id: 1, floor: 0, gridX: 0, gridY: 0 }),
        makeTile({ id: 2, floor: 1, gridX: 0, gridY: 0 }),
      ],
    });
    expect(screen.getByTestId('lattice-tile-1')).toBeInTheDocument();
    expect(screen.queryByTestId('lattice-tile-2')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('lattice-floor-1'));

    expect(screen.queryByTestId('lattice-tile-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('lattice-tile-2')).toBeInTheDocument();
  });
});

describe('Lattice — prune and connect tools', () => {
  it('are mutually exclusive', () => {
    renderLattice({ tiles: [] });
    fireEvent.click(screen.getByTestId('lattice-connect-toggle'));
    expect(screen.getByTestId('lattice-connect-toggle')).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByTestId('lattice-prune-toggle'));
    expect(screen.getByTestId('lattice-prune-toggle')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('lattice-connect-toggle')).toHaveAttribute('aria-pressed', 'false');
  });

  it('prune mode carves on a plain left click', () => {
    renderLattice({ tiles: [] });
    fireEvent.click(screen.getByTestId('lattice-prune-toggle'));
    fireEvent.click(screen.getByTestId('lattice-cell-0-0'));
    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'void');
  });

  it('the connect tool is not offered in areas mode', () => {
    renderLattice({ mode: 'areas', tiles: [] });
    expect(screen.queryByTestId('lattice-connect-toggle')).not.toBeInTheDocument();
  });

  it('links two adjacent rooms with direction-derived exit names and auto-exits connect mode', () => {
    const a = makeTile({ id: 1, name: 'Room A', gridX: 0, gridY: 0 });
    const b = makeTile({ id: 2, name: 'Room B', gridX: 1, gridY: 0 }); // east of A
    const { runAction } = renderLattice({ tiles: [a, b] });

    fireEvent.click(screen.getByTestId('lattice-connect-toggle'));
    fireEvent.click(screen.getByTestId('lattice-tile-1'));
    fireEvent.click(screen.getByTestId('lattice-tile-2'));

    expect(runAction).toHaveBeenCalledWith('staff_link_rooms', {
      room_a_id: 1,
      room_b_id: 2,
      name_ab: 'east',
      name_ba: 'west',
    });
    expect(screen.getByTestId('lattice-connect-toggle')).toHaveAttribute('aria-pressed', 'false');
  });

  it('gives non-adjacent rooms a fanciful ✦-style link instead of a direction word', () => {
    const a = makeTile({ id: 1, name: 'Room A', gridX: 0, gridY: 0 });
    const b = makeTile({ id: 2, name: 'Room B', gridX: 5, gridY: 5 });
    const { runAction } = renderLattice({ tiles: [a, b] });

    fireEvent.click(screen.getByTestId('lattice-connect-toggle'));
    fireEvent.click(screen.getByTestId('lattice-tile-1'));
    fireEvent.click(screen.getByTestId('lattice-tile-2'));

    const call = runAction.mock.calls.find(([key]) => key === 'staff_link_rooms');
    expect(call).toBeDefined();
    const [, kwargs] = call as [string, Record<string, unknown>];
    expect(kwargs.name_ab).not.toMatch(/^(north|south|east|west)$/);
  });

  it('clicking a tile while connecting does not open it', () => {
    const a = makeTile({ id: 1, gridX: 0, gridY: 0 });
    const b = makeTile({ id: 2, gridX: 1, gridY: 0 });
    const { onOpen } = renderLattice({ tiles: [a, b] });

    fireEvent.click(screen.getByTestId('lattice-connect-toggle'));
    fireEvent.click(screen.getByTestId('lattice-tile-1'));
    fireEvent.click(screen.getByTestId('lattice-tile-2'));

    expect(onOpen).not.toHaveBeenCalled();
  });
});

describe('Lattice — sketch persistence', () => {
  it('remembers a planned square across a remount for the same account/node', () => {
    const props: Partial<LatticeProps> = { nodeId: 42, tiles: [] };
    const first = renderLattice(props);
    fireEvent.click(screen.getByTestId('lattice-cell-0-0'));
    first.unmount();

    renderLattice(props);
    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'planned');
  });

  it('keeps a different node’s sketch separate', () => {
    const first = renderLattice({ nodeId: 1, tiles: [] });
    fireEvent.click(screen.getByTestId('lattice-cell-0-0'));
    first.unmount();

    renderLattice({ nodeId: 2, tiles: [] });
    expect(screen.getByTestId('lattice-cell-0-0')).toHaveAttribute('data-cell-state', 'empty');
  });
});

describe('Lattice — search-hit highlight (#3477 Task 6)', () => {
  it('marks the matching tile when highlightTileId is set, and no other tile', () => {
    const tiles = [
      makeTile({ id: 1, gridX: 0, gridY: 0 }),
      makeTile({ id: 2, gridX: 1, gridY: 0 }),
    ];
    renderLattice({ tiles, highlightTileId: 1 });

    expect(screen.getByTestId('lattice-tile-1')).toHaveAttribute('data-highlighted', 'true');
    expect(screen.getByTestId('lattice-tile-2')).not.toHaveAttribute('data-highlighted');
  });

  it('highlights nothing when highlightTileId is null', () => {
    const tiles = [makeTile({ id: 1, gridX: 0, gridY: 0 })];
    renderLattice({ tiles, highlightTileId: null });

    expect(screen.getByTestId('lattice-tile-1')).not.toHaveAttribute('data-highlighted');
  });
});
