/**
 * Shared node/edge composition for the grid-based map canvases: the
 * building builder canvas (#670, `@/buildings/components/BuilderCanvas`) and
 * the staff world-builder canvas (#2449,
 * `@/world-builder/components/WorldCanvas`). Both lay out placed rooms on
 * `cellToPosition`, park unplaced rooms in a tray column, compute ghost-dig
 * cells, pair exits into edges, and translate a node drag-stop back into a
 * grid cell for a place-room dispatch. Only the bits that differ between the
 * two canvases stay in the component: the room-node type/data shape (via
 * `nodeType`/`buildNodeData`), the ghost tooltip label, and the place-room
 * dispatch call itself (different REGISTRY key per app).
 *
 * The hook owns `useNodesState` internally (rather than leaving it to the
 * caller) so both canvases get identical recompute-on-payload-change wiring;
 * a caller only feeds it domain data and reads back `nodes`/`edges`/handlers
 * to pass into `MapCanvasShell`.
 */
import { useCallback, useEffect, useMemo } from 'react';
import { type Edge, type Node, useNodesState } from '@xyflow/react';

import { cellToPosition, positionToCell } from './coords';
import { exitEdges, type ExitEdge, type ExitRecord } from './edges';
import { ghostCells, type GhostCell } from './ghosts';

export interface GridRoomLike {
  id: number;
  grid_x: number | null;
  grid_y: number | null;
  floor: number;
}

export interface PlaceRoomArgs {
  roomId: number;
  grid_x: number;
  grid_y: number;
  floor: number;
}

export interface UseGridCanvasNodesArgs<TRoom extends GridRoomLike> {
  rooms: TRoom[];
  /** Exit pairs to render as edges — pre-filtered by the caller (e.g. #2449's
   * cross-area-exit exclusion) before reaching this hook. */
  exits: ExitRecord[];
  floor: number;
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  /** Room-node React Flow type key (`nodeTypes` in the caller). */
  nodeType: string;
  /** Builds the node `data` payload for a room; always merged with `{selected, onSelect}`. */
  buildNodeData: (room: TRoom) => Record<string, unknown>;
  /** Click on a ghost cell — omit to skip ghost-node rendering entirely. */
  onDigAt?: (ghost: GhostCell) => void;
  /** Ghost tooltip label — cell-based ("Dig room here") vs direction-based ("Dig <direction>"). */
  ghostLabel?: (ghost: GhostCell) => string;
  onExitClick?: (edge: ExitEdge) => void;
  onPlaceRoom: (args: PlaceRoomArgs) => void;
}

export interface UseGridCanvasNodesResult {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: ReturnType<typeof useNodesState<Node>>[2];
  onNodeDragStop: (event: React.MouseEvent | React.TouchEvent, node: Node) => void;
  onEdgeClick: (event: React.MouseEvent, edge: Edge) => void;
}

/**
 * Placed-room grid layout + unplaced-room tray + ghost cells + exit edges,
 * shared by every grid-based builder canvas. See module doc for what stays
 * component-specific.
 */
export function useGridCanvasNodes<TRoom extends GridRoomLike>({
  rooms,
  exits,
  floor,
  selectedRoomId,
  onSelectRoom,
  nodeType,
  buildNodeData,
  onDigAt,
  ghostLabel,
  onExitClick,
  onPlaceRoom,
}: UseGridCanvasNodesArgs<TRoom>): UseGridCanvasNodesResult {
  const { computedNodes, computedEdges, edgeById } = useMemo(() => {
    const onFloor = rooms.filter((room) => room.floor === floor);
    const placed = onFloor.filter((room) => room.grid_x !== null && room.grid_y !== null);
    const unplaced = onFloor.filter((room) => room.grid_x === null || room.grid_y === null);

    const trayX = (placed.length > 0 ? Math.min(...placed.map((room) => room.grid_x!)) : 0) - 2;
    const trayTopY = placed.length > 0 ? Math.max(...placed.map((room) => room.grid_y!)) : 0;

    const roomNodes: Node[] = [
      ...placed.map((room) => ({
        id: String(room.id),
        type: nodeType,
        position: cellToPosition({ x: room.grid_x!, y: room.grid_y! }),
        data: {
          ...buildNodeData(room),
          selected: room.id === selectedRoomId,
          onSelect: onSelectRoom,
        },
        draggable: true,
      })),
      ...unplaced.map((room, index) => ({
        id: String(room.id),
        type: nodeType,
        position: cellToPosition({ x: trayX, y: trayTopY - index }),
        data: {
          ...buildNodeData(room),
          selected: room.id === selectedRoomId,
          onSelect: onSelectRoom,
        },
        draggable: true,
      })),
    ];

    const ghosts = onDigAt
      ? ghostCells(
          rooms.map((room) => ({
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
            data: {
              ghost,
              onDig: onDigAt,
              label: ghostLabel ? ghostLabel(ghost) : `Dig ${ghost.direction}`,
            },
            draggable: false,
            selectable: false,
          })
        )
      : [];

    const placedIds = new Set(placed.map((room) => room.id));
    const pairs = exitEdges(exits).filter(
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
  }, [
    rooms,
    exits,
    floor,
    selectedRoomId,
    onSelectRoom,
    nodeType,
    buildNodeData,
    onDigAt,
    ghostLabel,
  ]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);

  useEffect(() => {
    setNodes(computedNodes);
  }, [computedNodes, setNodes]);

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent | React.TouchEvent, node: Node) => {
      if (node.type !== nodeType) return;
      const roomId = Number(node.id);
      if (Number.isNaN(roomId)) return;
      const cell = positionToCell(node.position);
      onPlaceRoom({ roomId, grid_x: cell.x, grid_y: cell.y, floor });
    },
    [onPlaceRoom, floor, nodeType]
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

  return { nodes, edges: computedEdges, onNodesChange, onNodeDragStop, onEdgeClick };
}
