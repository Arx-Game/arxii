/**
 * WorldCanvas — the staff world-builder map (#2449): an area's rooms on the
 * cosmetic grid, exit-pair edges, ghost cells to dig into, drag-to-place.
 * Structural mirror of `BuilderCanvas` (#670, `@/buildings/components/BuilderCanvas`)
 * over the `WorldBuilderAreaManager` shape instead of `BuildingManagerPayload`.
 *
 * The placed/unplaced-tray node layout, ghost-cell assembly, drag-stop →
 * place-room shape, and node/edge memoization are shared with
 * `BuilderCanvas` via `useGridCanvasNodes` (`@/map-canvas`, Sonar dedup fix
 * pass — the two canvases were byte-for-byte identical there apart from the
 * room-node data shape, ghost label, and REGISTRY key). This canvas supplies
 * its own cell-based ghost tooltip label ("Dig room here") rather than
 * buildings' direction-based one ("Dig <direction>"), and its own
 * `WorldRoomNode` data shape.
 *
 * Cross-area exits (`to_room_id === null`) are excluded from edge computation
 * — they render on the far side's own canvas, not as a dangling edge here;
 * the destination is still visible in the right-panel exit list via
 * `to_room_name`/`to_area_id`. That filter/narrow stays here (not generic to
 * the shared hook) since it's a world-builder-only concept.
 */
import { useCallback, useMemo } from 'react';

import { CELL } from '@/map-canvas/coords';
import type { ExitEdge, ExitRecord } from '@/map-canvas/edges';
import { GhostNode } from '@/map-canvas/GhostNode';
import type { GhostCell } from '@/map-canvas/ghosts';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';
import { useGridCanvasNodes, type PlaceRoomArgs } from '@/map-canvas/useGridCanvasNodes';

import type { WorldBuilderActionKey, WorldBuilderAreaManager, WorldBuilderRoom } from '../types';
import { WorldRoomNode } from './WorldRoomNode';

const nodeTypes = { room: WorldRoomNode, ghost: GhostNode };

const buildRoomNodeData = (room: WorldBuilderRoom) => ({ room });
const ghostLabel = () => 'Dig room here';

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
  // Cross-area exits (`to_room_id === null`) render on the far side's own
  // canvas — see module doc. Narrow to the shared `ExitRecord` shape (every
  // remaining exit has a real `to_room_id`) before handing off to the hook.
  const connectableExits: ExitRecord[] = useMemo(
    () =>
      payload.exits
        .filter((exit) => exit.to_room_id !== null)
        .map((exit) => ({
          id: exit.id,
          name: exit.name,
          from_room_id: exit.from_room_id,
          to_room_id: exit.to_room_id as number,
        })),
    [payload.exits]
  );

  const onPlaceRoom = useCallback(
    ({ roomId, grid_x, grid_y, floor: placedFloor }: PlaceRoomArgs) => {
      runAction('staff_place_room', { room_id: roomId, grid_x, grid_y, floor: placedFloor });
    },
    [runAction]
  );

  const { nodes, edges, onNodesChange, onNodeDragStop, onEdgeClick } = useGridCanvasNodes({
    rooms: payload.rooms,
    exits: connectableExits,
    floor,
    selectedRoomId,
    onSelectRoom,
    nodeType: 'room',
    buildNodeData: buildRoomNodeData,
    onDigAt,
    ghostLabel,
    onExitClick,
    onPlaceRoom,
  });

  return (
    <MapCanvasShell
      testId="world-canvas"
      nodes={nodes}
      edges={edges}
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
