/**
 * Custom React Flow nodes for the building builder canvas (#670).
 *
 * `RoomNode` — one placed (or tray-parked unplaced) room. One cell per room:
 * size renders as a badge, never as footprint. `GhostNode` — an empty cell
 * adjacent to a placed room; clicking it starts a dig prefilled with the
 * direction from its source room.
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

import { Badge } from '@/components/ui/badge';

import type { GhostCell } from '../gridMath';
import type { ManagerRoom } from '../types';

export interface RoomNodeData extends Record<string, unknown> {
  room: ManagerRoom;
  selected: boolean;
  onSelect: (roomId: number) => void;
}

export type RoomNodeType = Node<RoomNodeData>;

function RoomNodeComponent({ data }: NodeProps<RoomNodeType>) {
  const { room, selected } = data;
  return (
    <div
      role="button"
      tabIndex={0}
      className={`h-[104px] w-[104px] cursor-pointer overflow-hidden rounded-md border bg-card p-2 shadow-sm transition-colors hover:border-primary/60 ${
        selected ? 'border-primary ring-2 ring-primary/40' : 'border-border'
      }`}
      onClick={() => data.onSelect(room.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          data.onSelect(room.id);
        }
      }}
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

export interface GhostNodeData extends Record<string, unknown> {
  ghost: GhostCell;
  onDig: (ghost: GhostCell) => void;
}

export type GhostNodeType = Node<GhostNodeData>;

function GhostNodeComponent({ data }: NodeProps<GhostNodeType>) {
  return (
    <button
      type="button"
      className="flex h-[104px] w-[104px] items-center justify-center rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 text-2xl text-muted-foreground/50 transition-colors hover:border-primary/60 hover:text-primary"
      onClick={() => data.onDig(data.ghost)}
      title={`Dig ${data.ghost.direction}`}
      data-testid="builder-ghost-node"
    >
      +
    </button>
  );
}

export const GhostNode = memo(GhostNodeComponent);
