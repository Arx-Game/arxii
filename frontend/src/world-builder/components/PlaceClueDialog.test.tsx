import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PlaceClueDialog } from './PlaceClueDialog';

function renderDialog(overrides: Partial<Parameters<typeof PlaceClueDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <PlaceClueDialog
      roomId={5}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('PlaceClueDialog', () => {
  it('dispatches staff_place_clue with the room id, clue slug, and difficulty', async () => {
    const { runAction } = renderDialog();

    await userEvent.type(screen.getByLabelText(/clue slug/i), 'torn-letter');
    await userEvent.clear(screen.getByLabelText(/detect difficulty/i));
    await userEvent.type(screen.getByLabelText(/detect difficulty/i), '5');
    await userEvent.click(screen.getByTestId('place-clue-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_clue', {
      room_id: 5,
      clue_slug: 'torn-letter',
      detect_difficulty: 5,
    });
  });

  it('keeps the submit button disabled until a clue slug is entered', () => {
    renderDialog();
    expect(screen.getByTestId('place-clue-submit')).toBeDisabled();
  });
});
