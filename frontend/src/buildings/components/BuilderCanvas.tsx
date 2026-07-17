/**
 * BuilderCanvas — the building map (#670): rooms on the cosmetic grid,
 * exit-pair edges, ghost cells to dig into, drag-to-place.
 *
 * Coordinates come straight from the backend grid (north = +grid_y, drawn
 * upward). Placement is cosmetic-only: a drag dispatches `place_room` and
 * the manager payload refetch settles the truth. Unplaced rooms park in a
 * tray column left of the map and can be dragged onto the grid.
 *
 * Node/edge composition (placed grid layout, unplaced tray, ghost cells,
 * exit-pair edges, drag-stop → place-room shape) lives in the shared
 * `useGridCanvasNodes` hook (`@/map-canvas`) — also used by the staff
 * world-builder canvas (#2449, `@/world-builder/components/WorldCanvas`).
 * This component owns only the `RoomNode` data shape, the direction-based
 * ghost label, and the `place_room` REGISTRY key.
 */

import { useCallback } from 'react';

import { CELL } from '@/map-canvas/coords';
import type { ExitEdge } from '@/map-canvas/edges';
import { GhostNode } from '@/map-canvas/GhostNode';
import type { GhostCell } from '@/map-canvas/ghosts';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';
import { useGridCanvasNodes, type PlaceRoomArgs } from '@/map-canvas/useGridCanvasNodes';

import type { BuildingManagerPayload, ManagerRoom } from '../types';
import type { RoomBuilderActionKey } from '../types';
import { RoomNode } from './RoomNode';

const nodeTypes = { room: RoomNode, ghost: GhostNode };

const buildRoomNodeData = (room: ManagerRoom) => ({ room });

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

export function BuilderCanvas({
  payload,
  floor,
  selectedRoomId,
  onSelectRoom,
  onDigAt,
  onExitClick,
  runAction,
}: BuilderCanvasProps) {
  const onPlaceRoom = useCallback(
    ({ roomId, grid_x, grid_y, floor: placedFloor }: PlaceRoomArgs) => {
      runAction('place_room', { room_id: roomId, grid_x, grid_y, floor: placedFloor });
    },
    [runAction]
  );

  const { nodes, edges, onNodesChange, onNodeDragStop, onEdgeClick } = useGridCanvasNodes({
    rooms: payload.rooms,
    exits: payload.exits,
    floor,
    selectedRoomId,
    onSelectRoom,
    nodeType: 'room',
    buildNodeData: buildRoomNodeData,
    onDigAt,
    onExitClick,
    onPlaceRoom,
  });

  return (
    <MapCanvasShell
      testId="builder-canvas"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeDragStop={onNodeDragStop}
      onEdgeClick={onEdgeClick}
      snapToGrid
      snapGrid={[CELL, CELL]}
      backgroundGap={CELL}
    />
  );
}
