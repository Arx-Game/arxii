/**
 * BuilderCanvas — the building map (#670): rooms on the cosmetic grid,
 * exit-pair edges, ghost cells to dig into, drag-to-place.
 *
 * Coordinates come straight from the backend grid (north = +grid_y, drawn
 * upward). Placement is cosmetic-only: a drag dispatches `place_room` and
 * the manager payload refetch settles the truth. Unplaced rooms park in a
 * tray column left of the map and can be dragged onto the grid.
 */

import { useCallback, useEffect, useMemo } from 'react';
import {
  Background,
  Controls,
  type Edge,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
} from '@xyflow/react';

import {
  CELL,
  cellToPosition,
  exitEdges,
  ghostCells,
  positionToCell,
  type ExitEdge,
  type GhostCell,
} from '../gridMath';
import type { BuildingManagerPayload } from '../types';
import type { RoomBuilderActionKey } from '../types';
import { GhostNode, RoomNode } from './RoomNode';

import '@xyflow/react/dist/style.css';

const nodeTypes = { room: RoomNode, ghost: GhostNode };

export interface BuilderCanvasProps {
  payload: BuildingManagerPayload;
  floor: number;
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  /** Click on a ghost cell — open the dig dialog prefilled with direction. */
  onDigAt?: (ghost: GhostCell) => void;
  /** Click on an exit edge — surface rename/remove for the pair. */
  onExitClick?: (edge: ExitEdge) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

export function BuilderCanvas(props: BuilderCanvasProps) {
  return (
    <ReactFlowProvider>
      <BuilderCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function BuilderCanvasInner({
  payload,
  floor,
  selectedRoomId,
  onSelectRoom,
  onDigAt,
  onExitClick,
  runAction,
}: BuilderCanvasProps) {
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
    const pairs = exitEdges(payload.exits).filter(
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
      runAction('place_room', {
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
    <div className="h-full w-full" data-testid="builder-canvas">
      <ReactFlow
        nodes={nodes}
        edges={computedEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={onNodeDragStop}
        onEdgeClick={onEdgeClick}
        fitView
        snapToGrid
        snapGrid={[CELL, CELL]}
      >
        <Background gap={CELL} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
