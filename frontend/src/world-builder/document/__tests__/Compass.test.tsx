import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import type { WorldBuilderRoom } from '../../types';
import { Compass, type CompassProps } from '../Compass';

// `renderWithProviders`'s own `rerender` re-renders a bare element with no
// providers, which unmounts+remounts the whole tree (different root type) —
// fine for most tests, but it would also reset Compass's pendingRef, which
// is exactly what the dig-then-link test needs to survive a prop update.
// This keeps one stable provider tree across both calls.
const queryClient = new QueryClient();
function wrap(ui: React.ReactNode) {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}

// Compass's own tests care about its grid math and the dig-then-link
// deferral, not AddDialog's internal form mechanics (AddDialog.test.tsx
// already covers those) — a thin mock exposing onConfirm keeps this file
// focused, and lets us assert exactly what defaultNeighbor/roomOptions
// Compass computed.
vi.mock('../../atlas/AddDialog', () => ({
  AddDialog: ({
    open,
    onConfirm,
    defaultNeighbor,
    roomOptions,
  }: {
    open: boolean;
    onConfirm: (payload: unknown) => void;
    defaultNeighbor: { roomId: number; intoName: string; outName: string } | null;
    roomOptions: { id: number; name: string }[];
  }) =>
    open ? (
      <div data-testid="mock-add-dialog">
        <span data-testid="mock-default-neighbor">{JSON.stringify(defaultNeighbor)}</span>
        <span data-testid="mock-room-options">{roomOptions.map((o) => o.name).join(',')}</span>
        <button
          data-testid="mock-confirm-dig"
          onClick={() =>
            onConfirm({
              kind: 'room',
              name: 'The Undercroft',
              entrance: defaultNeighbor
                ? { roomId: defaultNeighbor.roomId, exitName: defaultNeighbor.intoName }
                : null,
              exit: defaultNeighbor
                ? { roomId: defaultNeighbor.roomId, exitName: defaultNeighbor.outName }
                : null,
            })
          }
        >
          confirm
        </button>
      </div>
    ) : null,
}));

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
    published_at: '2026-01-01T00:00:00Z',
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

const CURRENT_ROOM = { id: 1, name: 'The Grand Foyer', gridX: 0, gridY: 0, floor: 0 };

function baseProps(overrides: Partial<CompassProps> = {}): CompassProps {
  return {
    areaId: 5,
    currentRoom: CURRENT_ROOM,
    rooms: [],
    onOpenRoom: vi.fn(),
    runAction: vi.fn(),
    ...overrides,
  };
}

describe('Compass', () => {
  it('renders the current room as the inert center cell', () => {
    renderWithProviders(<Compass {...baseProps()} />);
    expect(screen.getByTestId('compass-here')).toHaveTextContent('The Grand Foyer');
  });

  it('renders a placed neighbor as a clickable cell and opens it', async () => {
    const onOpenRoom = vi.fn();
    const neighbor = makeRoom({ id: 200, name: 'The Kitchen', grid_x: 1, grid_y: 0, floor: 0 });
    renderWithProviders(<Compass {...baseProps({ rooms: [neighbor], onOpenRoom })} />);

    const cell = screen.getByTestId('compass-neighbor-200');
    expect(cell).toHaveTextContent('The Kitchen');
    await userEvent.click(cell);
    expect(onOpenRoom).toHaveBeenCalledWith(200);
  });

  it('shows an unplaced note and no ⊕ affordances when the current room has no grid position', () => {
    renderWithProviders(
      <Compass {...baseProps({ currentRoom: { ...CURRENT_ROOM, gridX: null, gridY: null } })} />
    );
    expect(screen.getByTestId('compass-unplaced-note')).toBeInTheDocument();
    expect(screen.queryByLabelText('build a neighboring room here')).not.toBeInTheDocument();
  });

  it('⊕ on the cardinal-east cell computes east/west default connection names', async () => {
    renderWithProviders(<Compass {...baseProps()} />);
    await userEvent.click(screen.getByTestId('compass-add-1-0'));

    expect(screen.getByTestId('mock-default-neighbor')).toHaveTextContent(
      JSON.stringify({ roomId: 1, intoName: 'east', outName: 'west' })
    );
  });

  it('⊕ on a diagonal cell falls back to the fanciful exit name', async () => {
    renderWithProviders(<Compass {...baseProps()} />);
    await userEvent.click(screen.getByTestId('compass-add-1-1'));

    expect(screen.getByTestId('mock-default-neighbor')).toHaveTextContent(
      JSON.stringify({ roomId: 1, intoName: 'a fated passage', outName: 'a fated passage' })
    );
  });

  it('confirming a dig dispatches staff_dig_room at the targeted neighbor cell', async () => {
    const runAction = vi.fn();
    renderWithProviders(<Compass {...baseProps({ runAction })} />);
    await userEvent.click(screen.getByTestId('compass-add-1-0'));
    await userEvent.click(screen.getByTestId('mock-confirm-dig'));

    expect(runAction).toHaveBeenCalledWith('staff_dig_room', {
      area_id: 5,
      name: 'The Undercroft',
      floor: 0,
      grid_x: 1,
      grid_y: 0,
    });
  });

  it('links the new room back once it appears in the rooms list — never a silent no-op ⊕', async () => {
    const runAction = vi.fn();
    const { rerender } = render(wrap(<Compass {...baseProps({ runAction })} />));
    await userEvent.click(screen.getByTestId('compass-add-1-0'));
    await userEvent.click(screen.getByTestId('mock-confirm-dig'));

    // Not linked yet — the dug room hasn't shown up in `rooms` yet.
    expect(runAction).not.toHaveBeenCalledWith('staff_link_rooms', expect.anything());

    const dugRoom = makeRoom({ id: 300, name: 'The Undercroft', grid_x: 1, grid_y: 0, floor: 0 });
    rerender(wrap(<Compass {...baseProps({ runAction, rooms: [dugRoom] })} />));

    expect(runAction).toHaveBeenCalledWith('staff_link_rooms', {
      room_a_id: 300,
      room_b_id: 1,
      name_ab: 'west',
      name_ba: 'east',
    });
  });
});
