import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PlacePortalAnchorDialog } from './PlacePortalAnchorDialog';

function renderDialog(overrides: Partial<Parameters<typeof PlacePortalAnchorDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <PlacePortalAnchorDialog
      roomId={5}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('PlacePortalAnchorDialog', () => {
  it('dispatches staff_place_portal_anchor with the room id, kind name, and anchor name', async () => {
    const { runAction } = renderDialog();

    await userEvent.type(screen.getByLabelText(/anchor kind/i), 'Mirror');
    await userEvent.type(screen.getByLabelText(/anchor name/i), 'a tall silvered mirror');
    await userEvent.click(screen.getByTestId('place-portal-anchor-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_portal_anchor', {
      room_id: 5,
      kind_name: 'Mirror',
      name: 'a tall silvered mirror',
    });
  });

  it('keeps the submit button disabled until both fields are filled', async () => {
    renderDialog();
    expect(screen.getByTestId('place-portal-anchor-submit')).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/anchor kind/i), 'Mirror');
    expect(screen.getByTestId('place-portal-anchor-submit')).toBeDisabled();
  });
});
