/**
 * FocusPanel tests.
 *
 * The component is a thin orchestrator over ``useFocusStack``: each
 * branch (room/character/item) is asserted by handing it a fake stack
 * api with the relevant ``current`` entry. The Back button only renders
 * at depth > 1 and delegates to ``focus.pop`` — both behaviors are
 * checked here.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { store } from '@/store/store';
import type { FocusEntry, FocusStackApi } from '@/inventory/hooks/useFocusStack';
import type { RoomData } from './RoomPanel';

import { FocusPanel } from './FocusPanel';

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: vi.fn() }),
}));

vi.mock('@/inventory/components/CharacterFocusView', () => ({
  CharacterFocusView: ({
    character,
    onItemClick,
  }: {
    character: { id: number; name: string };
    onItemClick: (i: { id: number; name: string }) => void;
  }) => (
    <div data-testid="mock-character-focus">
      <span>{character.name}</span>
      <button type="button" onClick={() => onItemClick({ id: 99, name: 'Mock Item' })}>
        Drill into mock item
      </button>
    </div>
  ),
}));

vi.mock('@/inventory/components/ItemFocusView', () => ({
  ItemFocusView: ({ item }: { item: { id: number; name: string } }) => (
    <div data-testid="mock-item-focus">{item.name}</div>
  ),
}));

function renderUI(ui: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </Provider>
  );
}

function makeRoomData(): RoomData {
  return {
    id: 42,
    name: 'Throne Room',
    description: 'Vast and imposing.',
    thumbnail_url: null,
    characters: [
      { dbref: '#100', name: 'Alice', thumbnail_url: null, commands: [] },
      { dbref: '#101', name: 'Bob', thumbnail_url: null, commands: [] },
    ],
    objects: [],
    exits: [],
  };
}

function makeFocusApi(current: FocusEntry, depth = 1): FocusStackApi {
  return {
    current,
    depth,
    push: vi.fn(),
    pop: vi.fn(),
    reset: vi.fn(),
  };
}

describe('FocusPanel', () => {
  it('renders RoomPanel when focus is the room', () => {
    const focus = makeFocusApi({ kind: 'room', room: null, sceneSummary: null }, 1);
    const roomData = makeRoomData();

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={roomData} sceneData={null} />
    );

    // RoomPanel renders the room name in its header.
    expect(screen.getByText('Throne Room')).toBeInTheDocument();
    // CharactersList renders the present characters.
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('renders CharacterFocusView when focus is a character', () => {
    const focus = makeFocusApi({ kind: 'character', character: { id: 7, name: 'Sera' } }, 2);

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={makeRoomData()} sceneData={null} />
    );

    expect(screen.getByTestId('mock-character-focus')).toBeInTheDocument();
    expect(screen.getByText('Sera')).toBeInTheDocument();
  });

  it('renders ItemFocusView when focus is an item', () => {
    const focus = makeFocusApi({ kind: 'item', item: { id: 9, name: 'Silver Brooch' } }, 3);

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={makeRoomData()} sceneData={null} />
    );

    expect(screen.getByTestId('mock-item-focus')).toHaveTextContent('Silver Brooch');
  });

  it('does NOT render the Back button at depth 1', () => {
    const focus = makeFocusApi({ kind: 'room', room: null, sceneSummary: null }, 1);

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={makeRoomData()} sceneData={null} />
    );

    expect(screen.queryByTestId('focus-back-button')).not.toBeInTheDocument();
  });

  it('renders the Back button at depth > 1 and calls focus.pop on click', () => {
    const focus = makeFocusApi({ kind: 'character', character: { id: 7, name: 'Sera' } }, 2);

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={makeRoomData()} sceneData={null} />
    );

    const back = screen.getByTestId('focus-back-button');
    expect(back).toBeInTheDocument();
    fireEvent.click(back);
    expect(focus.pop).toHaveBeenCalledTimes(1);
  });

  it('drilling into a character from the room pushes a character entry', () => {
    const focus = makeFocusApi({ kind: 'room', room: null, sceneSummary: null }, 1);
    const roomData = makeRoomData();

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={roomData} sceneData={null} />
    );

    // Click Alice in the CharactersList — onCharacterClick is wired by
    // FocusPanel and should push a character entry derived from her dbref.
    fireEvent.click(screen.getByRole('button', { name: /alice/i }));
    expect(focus.push).toHaveBeenCalledWith({
      kind: 'character',
      character: { id: 100, name: 'Alice' },
    });
  });

  it('drilling into an item from a character focus pushes an item entry', () => {
    const focus = makeFocusApi({ kind: 'character', character: { id: 7, name: 'Sera' } }, 2);

    renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={makeRoomData()} sceneData={null} />
    );

    fireEvent.click(screen.getByRole('button', { name: /drill into mock item/i }));
    expect(focus.push).toHaveBeenCalledWith({
      kind: 'item',
      item: { id: 99, name: 'Mock Item' },
    });
  });

  it('resets the stack to the new room when the room id changes', () => {
    const focus = makeFocusApi({ kind: 'room', room: null, sceneSummary: null }, 1);
    const initialRoom = makeRoomData();

    const { rerender } = renderUI(
      <FocusPanel focus={focus} roomCharacter="Hero" roomData={initialRoom} sceneData={null} />
    );

    expect(focus.reset).toHaveBeenCalledTimes(1);
    expect(focus.reset).toHaveBeenLastCalledWith({
      kind: 'room',
      room: expect.objectContaining({ dbref: '#42', name: 'Throne Room' }),
      sceneSummary: null,
    });

    // Simulate moving to a new room.
    const nextRoom: RoomData = { ...initialRoom, id: 88, name: 'Garden' };
    rerender(
      <Provider store={store}>
        <QueryClientProvider client={new QueryClient()}>
          <FocusPanel focus={focus} roomCharacter="Hero" roomData={nextRoom} sceneData={null} />
        </QueryClientProvider>
      </Provider>
    );

    expect(focus.reset).toHaveBeenCalledTimes(2);
    expect(focus.reset).toHaveBeenLastCalledWith({
      kind: 'room',
      room: expect.objectContaining({ dbref: '#88', name: 'Garden' }),
      sceneSummary: null,
    });
  });

  it('resets the stack when the active puppet changes in the same room', () => {
    // Two puppets can share a room. Without including ``roomCharacter``
    // in the effect deps, swapping puppets in the same room would leak
    // the previous puppet's focus stack into the new puppet's session.
    const focus = makeFocusApi({ kind: 'room', room: null, sceneSummary: null }, 1);
    const room = makeRoomData();

    const { rerender } = renderUI(
      <FocusPanel focus={focus} roomCharacter="Alice" roomData={room} sceneData={null} />
    );

    expect(focus.reset).toHaveBeenCalledTimes(1);

    // Simulate the player switching active puppet to ``Bob`` in the
    // same room — same roomData.id, same sceneData, only roomCharacter
    // changed. The focus stack must reset.
    rerender(
      <Provider store={store}>
        <QueryClientProvider client={new QueryClient()}>
          <FocusPanel focus={focus} roomCharacter="Bob" roomData={room} sceneData={null} />
        </QueryClientProvider>
      </Provider>
    );

    expect(focus.reset).toHaveBeenCalledTimes(2);
    expect(focus.reset).toHaveBeenLastCalledWith({
      kind: 'room',
      room: expect.objectContaining({ dbref: '#42', name: 'Throne Room' }),
      sceneSummary: null,
    });
  });
});
