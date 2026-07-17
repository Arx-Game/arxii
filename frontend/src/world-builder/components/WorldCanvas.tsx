/**
 * WorldCanvas — the staff world-builder map (#2449): an area's rooms on the
 * cosmetic grid, exit-pair edges, ghost cells to dig into, drag-to-place.
 * Structural mirror of `BuilderCanvas` (#670, `@/buildings/components/BuilderCanvas`)
 * over the `WorldBuilderAreaManager` shape instead of `BuildingManagerPayload`.
 *
 * Reuses `ghostCells`/`GhostNode` from `@/buildings` as-is rather than forking
 * them — both are already generic over any `{grid_x,grid_y,floor}` room shape
 * and dig-specific only in the sense of "empty adjacent cell", which applies
 * here unchanged (implementer's call for this slice — see task-6 report).
 *
 * Cross-area exits (`to_room_id === null`) are excluded from edge computation
 * — they render on the far side's own canvas, not as a dangling edge here;
 * the destination is still visible in the right-panel exit list via
 * `to_room_name`/`to_area_id`.
 */
import { useCallback, useEffect, useMemo } from 'react';
import { type Edge, type Node, useNodesState } from '@xyflow/react';

import { GhostNode } from '@/buildings/components/RoomNode';
import { ghostCells, type GhostCell } from '@/buildings/gridMath';
import { CELL, cellToPosition, positionToCell } from '@/map-canvas/coords';
import { exitEdges, type ExitEdge, type ExitRecord } from '@/map-canvas/edges';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';

import type { WorldBuilderActionKey, WorldBuilderAreaManager } from '../types';
import { WorldRoomNode } from './WorldRoomNode';

const nodeTypes = { room: WorldRoomNode, ghost: GhostNode };

export interface WorldCanvasProps {
  payload: WorldBuilderAreaManager;
  floor: number;
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  /** Click on a ghost cell — open the dig dialog prefilled with that cell. */
  onDigAt?: (ghost: GhostCell) => void;
  /** Click on an exit edge — surface rename/unlink for the pair. */
  onExitClick?: (edge: ExitEdge) => void;
  runAction: (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

export function WorldCanvas({
  payload,
  floor,
  selectedRoomId,
  onSelectRoom,
  onDigAt,
  onExitClick,
  runAction,
}: WorldCanvasProps) {
  const { computedNodes, computedEdges, edgeById } = useMemo(() => {
    const onFloor = payload.rooms.filter((room) => room.floor === floor);
    const placed = onFloor.filter((room) => room.grid_x !== null && room.grid_y !== null);
    const unplaced = onFloor.filter((room) => room.grid_x === null || room.grid_y === null);

    const trayX = (placed.length > 0 ? Math.min(...placed.map((room) => room.grid_x!)) : 0) - 2;
    const trayTopY = placed.length > 0 ? Math.max(...placed.map((room) => room.grid_y!)) : 0;

    const roomNodes: Node[] = [
      ...placed.map((room) => ({
        id: String(room.id),
        type: 'room',
        position: cellToPosition({ x: room.grid_x!, y: room.grid_y! }),
        data: { room, selected: room.id === selectedRoomId, onSelect: onSelectRoom },
        draggable: true,
      })),
      ...unplaced.map((room, index) => ({
        id: String(room.id),
        type: 'room',
        position: cellToPosition({ x: trayX, y: trayTopY - index }),
        data: { room, selected: room.id === selectedRoomId, onSelect: onSelectRoom },
        draggable: true,
      })),
    ];

    const ghosts = onDigAt
      ? ghostCells(
          payload.rooms.map((room) => ({
            id: room.id,
            grid_x: room.grid_x,
            grid_y: room.grid_y,
            floor: room.floor,
          })),
          floor
        ).map(
          (ghost): Node => ({
            id: `ghost-${ghost.x}-${ghost.y}`,
            type: 'ghost',
            position: cellToPosition(ghost),
            data: { ghost, onDig: onDigAt },
            draggable: false,
            selectable: false,
          })
        )
      : [];

    const placedIds = new Set(placed.map((room) => room.id));
    const connectable: ExitRecord[] = payload.exits
      .filter((exit) => exit.to_room_id !== null)
      .map((exit) => ({
        id: exit.id,
        name: exit.name,
        from_room_id: exit.from_room_id,
        to_room_id: exit.to_room_id as number,
      }));
    const pairs = exitEdges(connectable).filter(
      (pair) => placedIds.has(pair.source) && placedIds.has(pair.target)
    );
    const edges: Edge[] = pairs.map((pair) => ({
      id: pair.id,
      source: String(pair.source),
      target: String(pair.target),
      label: pair.there?.name ?? pair.back?.name ?? '',
      type: 'straight',
    }));
    const byId = new Map(pairs.map((pair) => [pair.id, pair]));
    return { computedNodes: [...ghosts, ...roomNodes], computedEdges: edges, edgeById: byId };
  }, [payload, floor, selectedRoomId, onSelectRoom, onDigAt]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);

  useEffect(() => {
    setNodes(computedNodes);
  }, [computedNodes, setNodes]);

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent | React.TouchEvent, node: Node) => {
      if (node.type !== 'room') return;
      const roomId = Number(node.id);
      if (Number.isNaN(roomId)) return;
      const cell = positionToCell(node.position);
      runAction('staff_place_room', {
        room_id: roomId,
        grid_x: cell.x,
        grid_y: cell.y,
        floor,
      });
    },
    [runAction, floor]
  );

  const onEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      const pair = edgeById.get(edge.id);
      if (pair && onExitClick) {
        onExitClick(pair);
      }
    },
    [edgeById, onExitClick]
  );

  return (
    <MapCanvasShell
      testId="world-canvas"
      nodes={nodes}
      edges={computedEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeDragStop={onNodeDragStop}
      onEdgeClick={onEdgeClick}
      snapToGrid
      snapGrid={[CELL, CELL]}
      backgroundGap={CELL}
      emptyState={
        payload.rooms.length === 0 ? (
          <div
            className="flex h-full w-full items-center justify-center text-sm text-muted-foreground"
            data-testid="world-canvas-empty"
          >
            No rooms dug into this area yet.
          </div>
        ) : undefined
      }
    />
  );
}
