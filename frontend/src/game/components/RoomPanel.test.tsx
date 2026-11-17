import { useState } from 'react';
import { fireEvent, screen, act, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import {
  resetGame,
  setSessionConnectionStatus,
  setRoomStateResyncStatus,
  startSession,
} from '@/store/gameSlice';
import { store } from '@/store/store';
import { RoomPanel } from './RoomPanel';

const mockConnect = vi.fn(() => Promise.resolve());
const mockRequestRoomState = vi.fn();
const mockSend = vi.fn();
const mockDispatch = vi.fn();

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: () => ({ mutateAsync: mockDispatch, isPending: false }),
}));

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({
    connect: mockConnect,
    requestRoomState: mockRequestRoomState,
    send: mockSend,
  }),
}));

const renderEmptyRoom = (character: string | null) =>
  renderWithProviders(<RoomPanel character={character} room={null} scene={null} />);

describe('RoomPanel location recovery', () => {
  afterEach(() => {
    // Components are still mounted here; reset inside act so they re-render cleanly.
    act(() => {
      store.dispatch(resetGame());
    });
    vi.clearAllMocks();
  });

  it('explains that a selected character is waiting for location data and can refresh it', () => {
    store.dispatch(startSession('Aria'));
    store.dispatch(setSessionConnectionStatus({ character: 'Aria', status: true }));

    renderEmptyRoom('Aria');

    expect(screen.getByText('Location not confirmed yet')).toBeInTheDocument();
    expect(
      screen.getByText('Connected as Aria, but the game has not confirmed your location yet.')
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh location' }));
    expect(mockRequestRoomState).toHaveBeenCalledWith('Aria');
    fireEvent.click(screen.getByRole('button', { name: 'Re-enter as Aria' }));
    expect(mockSend).toHaveBeenCalledWith('Aria', '@ic Aria');
    expect(screen.getByRole('link', { name: 'Return to Hall' })).toHaveAttribute('href', '/');
  });

  it('offers reconnect when the selected session is disconnected', () => {
    store.dispatch(startSession('Aria'));

    renderEmptyRoom('Aria');

    fireEvent.click(screen.getByRole('button', { name: 'Reconnect' }));
    expect(mockConnect).toHaveBeenCalledWith('Aria');
  });

  it('does not imply that a missing location is a connected character when none is selected', () => {
    renderEmptyRoom(null);

    expect(screen.getByText('Choose a character to enter the world')).toBeInTheDocument();
    expect(
      screen.getByText('Select a character above to see room information.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reconnect' })).not.toBeInTheDocument();
  });

  it('shows a failed refresh message without hiding the recovery actions', () => {
    store.dispatch(startSession('Aria'));
    store.dispatch(
      setRoomStateResyncStatus({
        character: 'Aria',
        status: 'failure',
        error: 'Room state refresh failed. Retry.',
      })
    );

    renderEmptyRoom('Aria');

    expect(screen.getByRole('alert')).toHaveTextContent('Room state refresh failed. Retry.');
    expect(screen.getByRole('link', { name: 'Return to Hall' })).toBeInTheDocument();
  });
});

describe('RoomPanel Primum', () => {
  const room = {
    id: 1,
    name: 'The Ashmouth Caldera',
    description: 'A cauldron of cooling rock.',
    thumbnail_url: null,
    characters: [],
    objects: [],
    exits: [],
    is_owner: false,
    is_public: true,
    hub: null,
  };

  afterEach(() => {
    act(() => {
      store.dispatch(resetGame());
    });
  });

  it('lists what the viewer senses under "You sense"', () => {
    renderWithProviders(
      <RoomPanel
        character="Aria"
        room={{
          ...room,
          primum: {
            sensed: [{ substance_id: 3, substance_name: 'fire', step_name: 'Massive' }],
            line: 'You sense fire Primum: Massive.',
            harvestable: [],
          },
        }}
        scene={null}
      />
    );

    expect(screen.getByText('You sense')).toBeInTheDocument();
    expect(screen.getByText('Fire Primum: Massive')).toBeInTheDocument();
    // Her own Gift's substance stays with her; no reminder that it fades.
    expect(screen.queryByText('You see this until you leave the place.')).not.toBeInTheDocument();
  });

  it('says a sighting lasts until she leaves the place', () => {
    renderWithProviders(
      <RoomPanel
        character="Aria"
        room={{
          ...room,
          primum: {
            sensed: [
              {
                substance_id: 3,
                substance_name: 'fire',
                step_name: 'Massive',
                from_sighting: true,
              },
              { substance_id: 4, substance_name: 'earth', step_name: 'Trace', from_sighting: true },
            ],
            line: 'You sense fire Primum: Massive. You sense earth Primum: Trace.',
            harvestable: [],
          },
        }}
        scene={null}
      />
    );

    const panel = within(screen.getByTestId('primum-panel'));
    const rows = panel.getAllByRole('listitem').map((item) => item.textContent);
    expect(rows).toEqual(['Fire Primum: Massive', 'Earth Primum: Trace']);
    expect(screen.getByText('You see this until you leave the place.')).toBeInTheDocument();
  });

  it('shows nothing about Primum the viewer does not sense', () => {
    renderWithProviders(
      <RoomPanel
        character="Aria"
        room={{ ...room, primum: { sensed: [], line: '', harvestable: [] } }}
        scene={null}
      />
    );

    expect(screen.queryByText('You sense')).not.toBeInTheDocument();
  });

  it('draws out the picked Primum and keeps the answer when the lair empties', async () => {
    mockDispatch.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Good success. You draw out 2 Fire Primum (Fine).',
      data: {
        remaining_line:
          'The Ashmouth Caldera now holds a Rich amount of fire Primum. It refills slowly.',
      },
    });
    const offer = {
      substance_id: 3,
      substance_name: 'fire',
      source: 'place',
      opponent_id: null,
      opponent_name: '',
      step_name: 'Massive',
      check_name: 'Harvesting',
      ap_cost: 2,
    };
    const primum = {
      sensed: [{ substance_id: 3, substance_name: 'fire', step_name: 'Massive' }],
      line: 'You sense fire Primum: Massive.',
      harvestable: [offer],
    };
    function Harness() {
      const [emptied, setEmptied] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setEmptied(true)}>
            empty the lair
          </button>
          <RoomPanel
            character="Aria"
            characterId={9}
            room={{
              ...room,
              primum: emptied ? { sensed: [], line: '', harvestable: [] } : primum,
            }}
            scene={null}
          />
        </>
      );
    }
    renderWithProviders(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'Harvest Primum' }));
    expect(screen.getByText('Draw out')).toBeInTheDocument();
    expect(screen.getByLabelText('Fire Primum · Massive')).toBeChecked();
    expect(screen.getByText('Check: Harvesting')).toBeInTheDocument();
    expect(screen.getByText('Costs 2 AP')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Harvest' }));

    expect(
      await screen.findByText('Good success. You draw out 2 Fire Primum (Fine).')
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'empty the lair' }));
    expect(
      screen.getByText(
        'The Ashmouth Caldera now holds a Rich amount of fire Primum. It refills slowly.'
      )
    ).toBeInTheDocument();
  });

  it('closes the harvest block when the lair empties with no answer held', () => {
    const offer = {
      substance_id: 3,
      substance_name: 'fire',
      source: 'place',
      opponent_id: null,
      opponent_name: '',
      step_name: 'Massive',
      check_name: 'Harvesting',
      ap_cost: 2,
    };
    function Harness() {
      const [emptied, setEmptied] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setEmptied(true)}>
            empty the lair
          </button>
          <RoomPanel
            character="Aria"
            characterId={9}
            room={{
              ...room,
              primum: { sensed: [], line: '', harvestable: emptied ? [] : [offer] },
            }}
            scene={null}
          />
        </>
      );
    }
    renderWithProviders(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'Harvest Primum' }));
    expect(screen.getByText('Draw out')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'empty the lair' }));

    expect(screen.queryByText('Draw out')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
  });
});
