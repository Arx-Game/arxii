/**
 * RoomAccessPanel (#2450 Fix round 1): the grant list is now purely a render
 * of the server-provided `grants` prop, not client-tracked state — verifies
 * a reload (a fresh mount with the same `grants` prop) still shows prior
 * grants, and that grant/revoke dispatch the right kwargs without mutating
 * any local list themselves.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';

import { RoomAccessPanel } from './RoomAccessPanel';

function renderPanel(overrides: Partial<Parameters<typeof RoomAccessPanel>[0]> = {}) {
  const runAccessAction = vi.fn(
    (
      _key: 'grant_story_room' | 'revoke_story_room',
      _kwargs: Record<string, unknown>,
      onSuccess: () => void
    ) => onSuccess()
  );
  renderWithProviders(
    <RoomAccessPanel roomId={5} grants={[]} runAccessAction={runAccessAction} {...overrides} />
  );
  return { runAccessAction };
}

describe('RoomAccessPanel', () => {
  it('shows the empty state when there are no grants', () => {
    renderPanel();
    expect(screen.getByText('No one has access yet.')).toBeInTheDocument();
  });

  it('renders every server-provided grant, surviving a fresh mount (a reload)', () => {
    renderPanel({ grants: ['Alice', 'Bob'] });
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.queryByText('No one has access yet.')).not.toBeInTheDocument();
  });

  it('dispatches grant_story_room with the room id and typed name', async () => {
    const { runAccessAction } = renderPanel();

    await userEvent.type(screen.getByTestId('room-access-name-input'), 'Charlie');
    await userEvent.click(screen.getByText('Grant'));

    expect(runAccessAction).toHaveBeenCalledWith(
      'grant_story_room',
      { room_id: 5, character_name: 'Charlie' },
      expect.any(Function)
    );
  });

  it('clears the name input on a successful grant', async () => {
    renderPanel();

    const input = screen.getByTestId('room-access-name-input') as HTMLInputElement;
    await userEvent.type(input, 'Charlie');
    await userEvent.click(screen.getByText('Grant'));

    expect(input.value).toBe('');
  });

  it('dispatches revoke_story_room with the room id and the grant being revoked', async () => {
    const { runAccessAction } = renderPanel({ grants: ['Alice'] });

    await userEvent.click(screen.getByText('Revoke'));

    expect(runAccessAction).toHaveBeenCalledWith(
      'revoke_story_room',
      { room_id: 5, character_name: 'Alice' },
      expect.any(Function)
    );
  });
});
