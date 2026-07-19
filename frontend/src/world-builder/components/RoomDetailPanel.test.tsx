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
  clues: [],
  clue_triggers: [],
  portal_anchors: [],
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

  it('lists clues, triggers, and portal anchors with remove buttons', async () => {
    const { runAction } = renderPanel({
      room: {
        ...room,
        clues: [
          {
            id: 1,
            clue_name: 'Torn Letter',
            clue_slug: 'torn-letter',
            detect_difficulty: 5,
            fixture_key: null,
          },
        ],
        clue_triggers: [{ id: 2, clue_name: 'Whisper', clue_slug: 'whisper', fixture_key: null }],
        portal_anchors: [{ id: 3, kind_name: 'Mirror', name: 'a mirror', fixture_key: null }],
      },
    });

    expect(screen.getByText('Torn Letter')).toBeInTheDocument();
    expect(screen.getByText('Whisper')).toBeInTheDocument();
    expect(screen.getByText('a mirror')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('remove-clue-1'));
    expect(runAction).toHaveBeenCalledWith('staff_remove_clue', { room_clue_id: 1 });

    await userEvent.click(screen.getByTestId('remove-clue-trigger-2'));
    expect(runAction).toHaveBeenCalledWith('staff_remove_clue_trigger', { clue_trigger_id: 2 });

    await userEvent.click(screen.getByTestId('remove-portal-anchor-3'));
    expect(runAction).toHaveBeenCalledWith('staff_remove_portal_anchor', { anchor_id: 3 });
  });

  it('opens PlaceClueDialog and dispatches staff_place_clue', async () => {
    const { runAction } = renderPanel();

    await userEvent.click(screen.getByText('Place clue'));
    await userEvent.type(await screen.findByLabelText(/clue slug/i), 'torn-letter');
    await userEvent.click(screen.getByTestId('place-clue-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_clue', {
      room_id: 5,
      clue_slug: 'torn-letter',
      detect_difficulty: 0,
    });
  });

  it('opens PlacePortalAnchorDialog and dispatches staff_place_portal_anchor', async () => {
    const { runAction } = renderPanel();

    await userEvent.click(screen.getByText('Place portal anchor'));
    await userEvent.type(await screen.findByLabelText(/anchor kind/i), 'Mirror');
    await userEvent.type(screen.getByLabelText(/anchor name/i), 'a mirror');
    await userEvent.click(screen.getByTestId('place-portal-anchor-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_portal_anchor', {
      room_id: 5,
      kind_name: 'Mirror',
      name: 'a mirror',
    });
  });
});

describe('RoomDetailPanel with palette="story"', () => {
  it('hides the fixture-key row, profile-flag toggles, and promote section', () => {
    renderPanel({ palette: 'story', room: { ...room, fixture_key: 'some-key' } });

    expect(screen.queryByText(/Fixture key:/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Publicly listed')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Social hub')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Outdoor')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Enclosure')).not.toBeInTheDocument();
    expect(screen.queryByText('Promote')).not.toBeInTheDocument();
    expect(screen.queryByText('Promote Grand Hall')).not.toBeInTheDocument();
  });

  it('hides exit renaming but keeps unlink', () => {
    renderPanel({ palette: 'story' });

    expect(screen.queryByText('Rename')).not.toBeInTheDocument();
    expect(screen.getByText('✕')).toBeInTheDocument();
  });

  it('dispatches story_edit_room with only name/description', async () => {
    const { runAction } = renderPanel({ palette: 'story' });

    await userEvent.clear(screen.getByLabelText('Name'));
    await userEvent.type(screen.getByLabelText('Name'), 'Throne Room');
    await userEvent.click(screen.getByText('Save changes'));

    expect(runAction).toHaveBeenCalledWith('story_edit_room', {
      room_id: 5,
      name: 'Throne Room',
    });
  });

  it('dispatches story_unlink_rooms for an exit removal', async () => {
    const { runAction } = renderPanel({ palette: 'story' });

    await userEvent.click(screen.getByText('✕'));

    expect(runAction).toHaveBeenCalledWith('story_unlink_rooms', { exit_id: 9 });
  });

  it('dispatches story_remove_room after confirming', async () => {
    const { runAction } = renderPanel({ palette: 'story' });

    await userEvent.click(screen.getByText('Remove Grand Hall'));
    await userEvent.click(await screen.findByRole('button', { name: 'Remove it' }));

    expect(runAction).toHaveBeenCalledWith('story_remove_room', { room_id: 5 });
  });
});
