import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ManagerRoom, RoomSizeTier } from '../types';
import { DigDialog } from './DigDialog';

const fromRoom: ManagerRoom = {
  id: 7,
  name: 'Entry Hall',
  description: '',
  is_public: false,
  size_name: 'Modest',
  size_units: 25,
  grid_x: 0,
  grid_y: 0,
  floor: 0,
  is_entry: true,
  tenancies: [],
};

const tiers: RoomSizeTier[] = [
  { id: 1, name: 'Snug', units: 10 },
  { id: 2, name: 'Modest', units: 25 },
];

function renderDialog(overrides: Partial<Parameters<typeof DigDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <DigDialog
      fromRoom={fromRoom}
      sizeTiers={tiers}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('DigDialog', () => {
  it('requires a direction and a name before digging', () => {
    renderDialog();
    expect(screen.getByTestId('dig-submit')).toBeDisabled();
  });

  it('dispatches dig_room with the anchor room_id and typed fields', async () => {
    const { runAction, onOpenChange } = renderDialog({ direction: 'north' });

    await userEvent.type(screen.getByLabelText('Room name'), 'Kitchen');
    await userEvent.click(screen.getByTestId('dig-submit'));

    expect(runAction).toHaveBeenCalledWith('dig_room', {
      room_id: 7,
      direction: 'north',
      name: 'Kitchen',
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('prefills like= for the duplicate flow', async () => {
    const { runAction } = renderDialog({ direction: 'east', like: 'West Corridor' });

    await userEvent.type(screen.getByLabelText('Room name'), 'East Corridor');
    await userEvent.click(screen.getByTestId('dig-submit'));

    expect(runAction).toHaveBeenCalledWith(
      'dig_room',
      expect.objectContaining({ like: 'West Corridor', direction: 'east' })
    );
  });
});
