import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderExit, WorldBuilderRoom } from '../types';
import { RoomDetailPanel } from './RoomDetailPanel';

const room: WorldBuilderRoom = {
  id: 5,
  name: 'Grand Hall',
  description: 'A hall.',
  is_public: true,
  is_social_hub: false,
  is_outdoor: false,
  enclosure: 'walled',
  size_name: 'Grand',
  grid_x: 0,
  grid_y: 0,
  floor: 0,
  fixture_key: null,
  origin: 'story',
  occupant_count: 2,
};

const exits: WorldBuilderExit[] = [
  { id: 9, name: 'north', from_room_id: 5, to_room_id: 6, to_room_name: 'Foyer', to_area_id: 1 },
];

function renderPanel(overrides: Partial<Parameters<typeof RoomDetailPanel>[0]> = {}) {
  const runAction = vi.fn();
  const onLinkRooms = vi.fn();
  renderWithProviders(
    <RoomDetailPanel
      room={room}
      exits={exits}
      runAction={runAction}
      onLinkRooms={onLinkRooms}
      {...overrides}
    />
  );
  return { runAction, onLinkRooms };
}

describe('RoomDetailPanel', () => {
  it('dispatches staff_edit_room with only the changed field', async () => {
    const { runAction } = renderPanel();

    await userEvent.clear(screen.getByLabelText('Name'));
    await userEvent.type(screen.getByLabelText('Name'), 'Throne Room');
    await userEvent.click(screen.getByText('Save changes'));

    expect(runAction).toHaveBeenCalledWith('staff_edit_room', {
      room_id: 5,
      name: 'Throne Room',
    });
  });

  it('leaves Save changes disabled until something is dirty', () => {
    renderPanel();
    expect(screen.getByText('Save changes')).toBeDisabled();
  });

  it('dispatches staff_rename_exit for a renamed exit', async () => {
    const { runAction } = renderPanel();

    const input = screen.getByDisplayValue('north');
    await userEvent.clear(input);
    await userEvent.type(input, 'south');
    await userEvent.click(screen.getByText('Rename'));

    expect(runAction).toHaveBeenCalledWith('staff_rename_exit', { exit_id: 9, name: 'south' });
  });

  it('dispatches staff_unlink_rooms for an exit removal', async () => {
    const { runAction } = renderPanel();

    await userEvent.click(screen.getByText('✕'));

    expect(runAction).toHaveBeenCalledWith('staff_unlink_rooms', { exit_id: 9 });
  });

  it('opens the link-rooms dialog', async () => {
    const { onLinkRooms } = renderPanel();

    await userEvent.click(screen.getByText('Link to another room'));

    expect(onLinkRooms).toHaveBeenCalled();
  });

  it('dispatches promote_room after confirming', async () => {
    const { runAction } = renderPanel();

    await userEvent.click(screen.getByText('Promote Grand Hall'));
    await userEvent.click(await screen.findByRole('button', { name: 'Promote' }));

    expect(runAction).toHaveBeenCalledWith('promote_room', { room_id: 5 });
  });

  it('disables Promote for an already-authored room', () => {
    renderPanel({ room: { ...room, origin: 'authored' } });
    expect(screen.getByText('Promote Grand Hall')).toBeDisabled();
  });

  it('dispatches staff_remove_room after confirming', async () => {
    const { runAction } = renderPanel();

    await userEvent.click(screen.getByText('Remove Grand Hall'));
    await userEvent.click(await screen.findByRole('button', { name: 'Remove it' }));

    expect(runAction).toHaveBeenCalledWith('staff_remove_room', { room_id: 5 });
  });
});
