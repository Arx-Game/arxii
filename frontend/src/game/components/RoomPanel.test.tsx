import { fireEvent, screen } from '@testing-library/react';
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
    store.dispatch(resetGame());
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
    expect(screen.getByRole('link', { name: 'Return to Hall' })).toHaveAttribute('href', '/hall');
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
