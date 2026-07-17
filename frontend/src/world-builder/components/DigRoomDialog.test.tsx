import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { DigRoomDialog } from './DigRoomDialog';

function renderDialog(overrides: Partial<Parameters<typeof DigRoomDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <DigRoomDialog
      areaId={1}
      floor={0}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('DigRoomDialog', () => {
  it('omits fixture_key entirely when left blank', async () => {
    const { runAction } = renderDialog();

    await userEvent.type(screen.getByLabelText('Room name'), 'Market Square');
    await userEvent.click(screen.getByTestId('dig-room-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_dig_room', {
      area_id: 1,
      name: 'Market Square',
      floor: 0,
    });
    const kwargs = runAction.mock.calls[0][1];
    expect(kwargs).not.toHaveProperty('fixture_key');
  });

  it('includes an explicit fixture_key in the dispatch kwargs', async () => {
    const { runAction } = renderDialog();

    await userEvent.type(screen.getByLabelText('Room name'), 'Market Square');
    await userEvent.type(screen.getByLabelText('Fixture key (optional)'), 'arx-city/market-square');
    await userEvent.click(screen.getByTestId('dig-room-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_dig_room', {
      area_id: 1,
      name: 'Market Square',
      floor: 0,
      fixture_key: 'arx-city/market-square',
    });
  });
});
