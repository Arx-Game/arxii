import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { editRoom } from '@/game/api/roomEditor';
import { RoomEditorPanel } from './RoomEditorPanel';

vi.mock('@/game/api/roomEditor', () => ({ editRoom: vi.fn() }));

function renderPanel(overrides: Partial<Parameters<typeof RoomEditorPanel>[0]> = {}) {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  renderWithProviders(
    <RoomEditorPanel
      characterId={42}
      initialName="Hall"
      initialDescription="Old desc."
      initialIsPublic={false}
      onSaved={onSaved}
      onCancel={onCancel}
      {...overrides}
    />
  );
  return { onSaved, onCancel };
}

describe('RoomEditorPanel', () => {
  it('dispatches edit_room with the edited fields and calls onSaved on success', async () => {
    vi.mocked(editRoom).mockResolvedValue('Room updated.');
    const { onSaved } = renderPanel();

    const nameInput = screen.getByLabelText('Room name');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'The Solar');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(editRoom).toHaveBeenCalledWith(42, expect.objectContaining({ name: 'The Solar' }));
      expect(onSaved).toHaveBeenCalled();
    });
  });

  it('does not call onSaved when the edit is refused', async () => {
    vi.mocked(editRoom).mockRejectedValue(new Error("You don't own this room."));
    const { onSaved } = renderPanel();

    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(editRoom).toHaveBeenCalled();
    });
    expect(onSaved).not.toHaveBeenCalled();
  });
});
