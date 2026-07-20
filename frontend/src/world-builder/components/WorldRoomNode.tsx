/**
 * WorldRoomNode — one room node in the staff world-builder canvas (#2449).
 * Structural sibling of buildings' `RoomNode` (`@/buildings/components/RoomNode`),
 * but surfaces the staff-only bookkeeping this canvas exists to manage instead
 * of building-tenancy data: fixture-key badge, origin (AUTHORED/STORY/PLAYER),
 * and occupant count.
 */
import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

import { Badge } from '@/components/ui/badge';
import { useMapNodeInteraction } from '@/map-canvas/useMapNodeInteraction';

import type { WorldBuilderRoom } from '../types';

export interface WorldRoomNodeData extends Record<string, unknown> {
  room: WorldBuilderRoom;
  selected: boolean;
  onSelect: (roomId: number) => void;
}

export type WorldRoomNodeType = Node<WorldRoomNodeData>;

function WorldRoomNodeComponent({ data }: NodeProps<WorldRoomNodeType>) {
  const { room, selected } = data;
  const interaction = useMapNodeInteraction({ onSelect: () => data.onSelect(room.id) });
  return (
    <div
      {...interaction}
      className={`h-[104px] w-[104px] cursor-pointer overflow-hidden rounded-md border bg-card p-2 shadow-sm transition-colors hover:border-primary/60 ${
        selected ? 'border-primary ring-2 ring-primary/40' : 'border-border'
      }`}
      data-testid="world-room-node"
      data-room-id={room.id}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <p className="truncate text-xs font-semibold text-foreground">{room.name}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        <Badge variant={room.origin === 'authored' ? 'default' : 'secondary'}>{room.origin}</Badge>
        {room.fixture_key && <Badge variant="outline">{room.fixture_key}</Badge>}
        {room.occupant_count > 0 && <Badge variant="outline">{room.occupant_count} pc</Badge>}
        {(room.clues.length > 0 || room.clue_triggers.length > 0) && (
          <Badge variant="outline" data-testid="world-room-clue-badge">
            {room.clues.length + room.clue_triggers.length} clues
          </Badge>
        )}
      </div>
      {!room.is_public && (
        <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">private</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}

export const WorldRoomNode = memo(WorldRoomNodeComponent);
