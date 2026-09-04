import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';

// `renderWithProviders`'s own `rerender` remounts the whole tree (bare
// element, different root type), which resets `pendingExitLinkRef` — the
// dig-then-link test needs one stable provider tree across both renders,
// same pattern as Compass.test.tsx.
const stableQueryClient = new QueryClient();
function wrap(ui: React.ReactNode) {
  return (
    <Provider store={store}>
      <QueryClientProvider client={stableQueryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}
import type {
  WorldBuilderAreaManager,
  WorldBuilderRoom,
  WorldBuilderRoomDetail,
} from '../../types';
import { RoomDocument } from '../RoomDocument';

// RoomDocument's own tests care about its wiring (which action gets which
// kwargs, the loading gate, draft restore, unpublished flag, next-unpublished
// cycling) — each child component already has its own focused test file, so
// thin mocks keep this file from re-testing their internals.
vi.mock('../../queries', () => ({
  useRoomDetailQuery: vi.fn(),
  useAreaManagerQuery: vi.fn(),
  useWorldBuilderAction: vi.fn(),
  useRoomSearchQuery: vi.fn(),
}));
vi.mock('../../useWorldBuilderActor', () => ({ useWorldBuilderActor: vi.fn(() => 1) }));
vi.mock('../Compass', () => ({
  Compass: ({ currentRoom }: { currentRoom: { id: number } }) => (
    <div data-testid="mock-compass" data-room-id={currentRoom.id} />
  ),
}));
vi.mock('../Marginalia', () => ({
  Marginalia: ({ onAddExit }: { onAddExit: () => void }) => (
    <div data-testid="mock-marginalia">
      <button data-testid="mock-open-add-exit" onClick={onAddExit}>
        add exit
      </button>
    </div>
  ),
}));
vi.mock('../ExitEditorDialog', () => ({
  ExitEditorDialog: () => null,
}));
vi.mock('../PreviewDialog', () => ({
  PreviewDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="mock-preview" /> : null,
}));
vi.mock('../VariantsPanel', () => ({
  VariantsPanel: () => <div data-testid="mock-variants" />,
}));
vi.mock('../../atlas/AddDialog', () => ({
  AddDialog: ({ open, onConfirm }: { open: boolean; onConfirm: (payload: unknown) => void }) =>
    open ? (
      <div data-testid="mock-add-dialog">
        <button
          data-testid="mock-confirm-exit-dig"
          onClick={() =>
            onConfirm({
              kind: 'exit',
              name: 'The Cellar',
              matchedRoomId: null,
              exitThere: 'down',
              exitBack: 'up',
            })
          }
        >
          dig it
        </button>
      </div>
    ) : null,
}));

const { useRoomDetailQuery, useAreaManagerQuery, useWorldBuilderAction, useRoomSearchQuery } =
  await import('../../queries');

function makeRoom(overrides: Partial<WorldBuilderRoom> = {}): WorldBuilderRoom {
  return {
    id: 100,
    name: 'The Grand Foyer',
    description: 'A hall meant to impress.',
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

function makeDetail(room: WorldBuilderRoom): WorldBuilderRoomDetail {
  return {
    id: room.id,
    room,
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
    breadcrumb: [{ id: 5, name: 'The Grand Foyer Building', level_display: 'Building' }],
    exits: [],
    comfort: { level: 0, points: 0, amenity: 0, axes: [] },
    ambient_lines: [],
    ambient_emits: [],
    resonances: [],
    dominant_affinity: null,
  };
}

function makeManager(rooms: WorldBuilderRoom[]): WorldBuilderAreaManager {
  return {
    area: {
      id: 5,
      name: 'The Grand Foyer Building',
      slug: null,
      level: 10,
      level_display: 'Building',
      origin: 'authored',
      parent: null,
      children_count: 0,
      grid_x: null,
      grid_y: null,
      realm: null,
      climate: null,
      dominant_society: null,
      effective_climate: null,
      art_url: null,
      description: '',
      color: '',
      permit_eligibility: 'open',
    },
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
    breadcrumb: [],
    rooms,
    resonances: [],
    exits: [],
  };
}

function mockQueries({
  room,
  managerRooms = [room],
}: {
  room: WorldBuilderRoom;
  managerRooms?: WorldBuilderRoom[];
}) {
  vi.mocked(useRoomDetailQuery).mockReturnValue({ data: makeDetail(room) } as never);
  vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(managerRooms) } as never);
  vi.mocked(useRoomSearchQuery).mockReturnValue({ data: [] } as never);
}

describe('RoomDocument', () => {
  let runMutation: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    runMutation = vi.fn();
    vi.mocked(useWorldBuilderAction).mockReturnValue({ mutate: runMutation } as never);
  });

  it('shows a loading state before the room detail loads', () => {
    vi.mocked(useRoomDetailQuery).mockReturnValue({ data: undefined } as never);
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: undefined } as never);
    vi.mocked(useRoomSearchQuery).mockReturnValue({ data: [] } as never);

    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);

    expect(screen.getByTestId('room-document-loading')).toBeInTheDocument();
  });

  it('shows the unpublished flag on an unpublished room', () => {
    mockQueries({ room: makeRoom({ published_at: null }) });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByTestId('unpublished-flag')).toBeInTheDocument();
  });

  it('hides the unpublished flag on a published room', () => {
    mockQueries({ room: makeRoom({ published_at: '2026-01-01T00:00:00Z' }) });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.queryByTestId('unpublished-flag')).not.toBeInTheDocument();
  });

  it('starts from the server name/description when no draft exists', () => {
    mockQueries({ room: makeRoom() });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByTestId('room-name-input')).toHaveValue('The Grand Foyer');
    expect(screen.getByTestId('room-description-input')).toHaveValue('A hall meant to impress.');
  });

  it('silently restores a left-over draft instead of the server value', () => {
    window.localStorage.setItem('world-builder-draft:100:name', 'Renamed mid-edit');
    window.localStorage.setItem('world-builder-draft:100:description', 'Half-written prose');
    mockQueries({ room: makeRoom() });

    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);

    expect(screen.getByTestId('room-name-input')).toHaveValue('Renamed mid-edit');
    expect(screen.getByTestId('room-description-input')).toHaveValue('Half-written prose');
  });

  it('Save dispatches staff_edit_room with the current draft text', async () => {
    mockQueries({ room: makeRoom() });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);

    const nameInput = screen.getByTestId('room-name-input');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'The Renamed Foyer');
    await userEvent.click(screen.getByTestId('save-button'));

    expect(runMutation).toHaveBeenCalledWith(
      {
        key: 'staff_edit_room',
        kwargs: {
          room_id: 100,
          name: 'The Renamed Foyer',
          description: 'A hall meant to impress.',
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('Save clears the draft on a successful dispatch', async () => {
    mockQueries({ room: makeRoom() });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    await userEvent.type(screen.getByTestId('room-name-input'), ' extra');
    await userEvent.click(screen.getByTestId('save-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: true, message: 'ok' });

    expect(window.localStorage.getItem('world-builder-draft:100:name')).toBeNull();
  });

  it('Save does NOT clear the draft on a business-rule refusal', async () => {
    mockQueries({ room: makeRoom() });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    await userEvent.type(screen.getByTestId('room-name-input'), ' extra');
    await userEvent.click(screen.getByTestId('save-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: false, message: 'Name the room.' });

    expect(window.localStorage.getItem('world-builder-draft:100:name')).not.toBeNull();
  });

  it('Publish dispatches staff_publish_room', async () => {
    mockQueries({ room: makeRoom() });
    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    await userEvent.click(screen.getByTestId('publish-button'));

    expect(runMutation).toHaveBeenCalledWith({
      key: 'staff_publish_room',
      kwargs: { room_id: 100 },
    });
  });

  it('Next unpublished cycles to the next unpublished sibling, wrapping around', async () => {
    const current = makeRoom({ id: 100, published_at: null });
    const other = makeRoom({ id: 101, name: 'The Undercroft', published_at: null });
    mockQueries({ room: current, managerRooms: [current, other] });
    const onNavigateRoom = vi.fn();

    renderWithProviders(
      <RoomDocument roomId={100} onNavigateRoom={onNavigateRoom} onDeleted={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId('next-unpublished-button'));

    expect(onNavigateRoom).toHaveBeenCalledWith(101);
  });

  it('disables Next unpublished when nothing in the area is unpublished', () => {
    const current = makeRoom({ id: 100, published_at: '2026-01-01T00:00:00Z' });
    mockQueries({ room: current, managerRooms: [current] });

    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByTestId('next-unpublished-button')).toBeDisabled();
  });

  it('delete: confirming dispatches staff_remove_room and calls onDeleted on success', async () => {
    mockQueries({ room: makeRoom() });
    const onDeleted = vi.fn();

    renderWithProviders(
      <RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(screen.getByTestId('delete-button'));
    await userEvent.click(screen.getByTestId('confirm-delete-button'));

    expect(runMutation).toHaveBeenCalledWith(
      { key: 'staff_remove_room', kwargs: { room_id: 100 } },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: true, message: 'Room removed.' });
    expect(onDeleted).toHaveBeenCalledWith(5);
  });

  it('exit dig: a same-area namesake links instead of digging a duplicate', async () => {
    // The dialog's matchedRoomId rides the async search; a submit that
    // outruns it reports null — the sibling list already in hand must catch
    // the match before the dig fork wins.
    const current = makeRoom({ id: 100 });
    const namesake = makeRoom({ id: 200, name: 'The Cellar' });
    mockQueries({ room: current, managerRooms: [current, namesake] });

    renderWithProviders(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />);
    await userEvent.click(screen.getByTestId('mock-open-add-exit'));
    await userEvent.click(screen.getByTestId('mock-confirm-exit-dig'));

    expect(runMutation).toHaveBeenCalledWith({
      key: 'staff_link_rooms',
      kwargs: { room_a_id: 100, room_b_id: 200, name_ab: 'down', name_ba: 'up' },
    });
    expect(runMutation).not.toHaveBeenCalledWith(
      expect.objectContaining({ key: 'staff_dig_room' })
    );
  });

  it('exit dig: the pending link resolves the NEW room by known-ids, then wires both ways', async () => {
    const current = makeRoom({ id: 100 });
    mockQueries({ room: current, managerRooms: [current] });

    const { rerender } = render(
      wrap(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />)
    );
    await userEvent.click(screen.getByTestId('mock-open-add-exit'));
    await userEvent.click(screen.getByTestId('mock-confirm-exit-dig'));

    expect(runMutation).toHaveBeenCalledWith({
      key: 'staff_dig_room',
      kwargs: { area_id: 5, name: 'The Cellar' },
    });
    expect(runMutation).not.toHaveBeenCalledWith(
      expect.objectContaining({ key: 'staff_link_rooms' })
    );

    // The refetch lands with the dug room; only the id NOT known at dig time
    // may receive the links.
    const dug = makeRoom({ id: 300, name: 'The Cellar' });
    mockQueries({ room: current, managerRooms: [current, dug] });
    rerender(wrap(<RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={vi.fn()} />));

    expect(runMutation).toHaveBeenCalledWith({
      key: 'staff_link_rooms',
      kwargs: { room_a_id: 300, room_b_id: 100, name_ab: 'up', name_ba: 'down' },
    });
  });

  it('delete: a refusal does not call onDeleted (the shared mutation hook already toasts the exact message)', async () => {
    mockQueries({ room: makeRoom() });
    const onDeleted = vi.fn();

    renderWithProviders(
      <RoomDocument roomId={100} onNavigateRoom={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(screen.getByTestId('delete-button'));
    await userEvent.click(screen.getByTestId('confirm-delete-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({
      success: false,
      message: 'Exported rooms are removed via the report-never-delete pipeline, not the canvas.',
    });
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
