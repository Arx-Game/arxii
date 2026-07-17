/**
 * Custom React Flow node for the building builder canvas (#670).
 *
 * `RoomNode` — one placed (or tray-parked unplaced) room. One cell per room:
 * size renders as a badge, never as footprint. The ghost-cell node
 * (`GhostNode`) moved to `@/map-canvas/GhostNode` (#2449 fix pass) — shared
 * with the staff world-builder canvas.
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

import { Badge } from '@/components/ui/badge';
import { useMapNodeInteraction } from '@/map-canvas/useMapNodeInteraction';

import type { ManagerRoom } from '../types';

export interface RoomNodeData extends Record<string, unknown> {
  room: ManagerRoom;
  selected: boolean;
  onSelect: (roomId: number) => void;
}

export type RoomNodeType = Node<RoomNodeData>;

function RoomNodeComponent({ data }: NodeProps<RoomNodeType>) {
  const { room, selected } = data;
  const interaction = useMapNodeInteraction({ onSelect: () => data.onSelect(room.id) });
  return (
    <div
      {...interaction}
      className={`h-[104px] w-[104px] cursor-pointer overflow-hidden rounded-md border bg-card p-2 shadow-sm transition-colors hover:border-primary/60 ${
        selected ? 'border-primary ring-2 ring-primary/40' : 'border-border'
      }`}
      data-testid="builder-room-node"
      data-room-id={room.id}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <p className="truncate text-xs font-semibold text-foreground">{room.name}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {room.is_entry && <Badge variant="secondary">Entry</Badge>}
        {room.size_name && <Badge variant="outline">{room.size_name}</Badge>}
        {room.tenancies.length > 0 && (
          <Badge variant="outline">
            {room.tenancies.length} {room.tenancies.length === 1 ? 'tenant' : 'tenants'}
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

export const RoomNode = memo(RoomNodeComponent);
