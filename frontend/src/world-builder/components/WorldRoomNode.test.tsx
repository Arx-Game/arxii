import { screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderRoom } from '../types';
import { WorldRoomNode } from './WorldRoomNode';

const baseRoom: WorldBuilderRoom = {
  id: 1,
  name: 'Golden Hart Taproom',
  description: '',
  is_public: true,
  is_social_hub: true,
  is_outdoor: false,
  enclosure: 'walled',
  size_name: null,
  grid_x: 0,
  grid_y: 0,
  floor: 0,
  fixture_key: 'arx-city/golden-hart-taproom',
  origin: 'authored',
  occupant_count: 0,
  clues: [],
  clue_triggers: [],
  portal_anchors: [],
};

function renderNode(room: WorldBuilderRoom) {
  return renderWithProviders(
    <ReactFlowProvider>
      <WorldRoomNode
        id="1"
        type="room"
        data={{ room, selected: false, onSelect: () => {} }}
        selected={false}
        selectable={false}
        deletable={false}
        draggable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    </ReactFlowProvider>
  );
}

describe('WorldRoomNode', () => {
  it('shows no clue badge when the room has no clues', () => {
    renderNode(baseRoom);
    expect(screen.queryByTestId('world-room-clue-badge')).not.toBeInTheDocument();
  });

  it('shows a clue count badge when the room has clues', () => {
    renderNode({
      ...baseRoom,
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
    });
    expect(screen.getByTestId('world-room-clue-badge')).toHaveTextContent('2 clues');
  });
});
