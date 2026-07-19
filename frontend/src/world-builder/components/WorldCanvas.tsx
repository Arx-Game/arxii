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
import {
  portalEdges,
  type ExitEdge,
  type ExitRecord,
  type PortalAnchorRecord,
} from '@/map-canvas/edges';
import { GhostNode } from '@/map-canvas/GhostNode';
import type { GhostCell } from '@/map-canvas/ghosts';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';
import { useGridCanvasNodes, type PlaceRoomArgs } from '@/map-canvas/useGridCanvasNodes';

import type { WorldBuilderAreaManager, WorldBuilderRoom } from '../types';
import { WorldRoomNode } from './WorldRoomNode';

const nodeTypes = { room: WorldRoomNode, ghost: GhostNode };

const buildRoomNodeData = (room: WorldBuilderRoom) => ({ room });
const ghostLabel = () => 'Dig room here';

/**
 * Pair same-kind portal anchors across an area's rooms into `PortalAnchorRecord`s —
 * "canvas shows where it leads" (#2451). Purely client-side heuristic: the
 * server doesn't resolve a destination for a portal anchor, so pair
 * sequentially within each kind (first<->second, third<->fourth, ...); a lone
 * anchor of a kind contributes no edge (still visible via the room's detail
 * panel). Extracted to module scope (not inlined in the `useMemo` below) so
 * this nontrivial edge-case logic is unit-testable without a component-render
 * harness — see `WorldCanvas.test.tsx`.
 */
export function pairPortalAnchors(rooms: WorldBuilderAreaManager['rooms']): PortalAnchorRecord[] {
  const byKind = new Map<string, { id: number; room_id: number; kind_name: string }[]>();
  for (const room of rooms) {
    for (const anchor of room.portal_anchors) {
      const list = byKind.get(anchor.kind_name) ?? [];
      list.push({ id: anchor.id, room_id: room.id, kind_name: anchor.kind_name });
      byKind.set(anchor.kind_name, list);
    }
  }
  const records: PortalAnchorRecord[] = [];
  for (const anchors of byKind.values()) {
    // Pair sequentially within the same kind — first↔second, third↔fourth, …
    // A lone anchor of a kind (no pair yet) contributes no edge, matching
    // exitEdges' one-way-exit precedent of "still valid, just no visual pair."
    for (let i = 0; i + 1 < anchors.length; i += 2) {
      records.push({ ...anchors[i], destination_room_id: anchors[i + 1].room_id });
      records.push({ ...anchors[i + 1], destination_room_id: anchors[i].room_id });
    }
  }
  return records;
}

export interface WorldCanvasProps {
  payload: WorldBuilderAreaManager;
  floor: number;
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  /** Click on a ghost cell — open the dig dialog prefilled with that cell. */
  onDigAt?: (ghost: GhostCell) => void;
  /** Click on an exit edge — surface rename/unlink for the pair. */
  onExitClick?: (edge: ExitEdge) => void;
  /** Keyed generically (not `WorldBuilderActionKey`) so the story palette's own action-key union type-checks too (#2450). */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
  /** `'story'` (#2450) dispatches `story_place_room` instead of `staff_place_room`. Defaults to `'staff'`. */
  palette?: 'staff' | 'story';
}

export function WorldCanvas({
  payload,
  floor,
  selectedRoomId,
  onSelectRoom,
  onDigAt,
  onExitClick,
  runAction,
  palette = 'staff',
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

  // Pairing heuristic lives in `pairPortalAnchors` above; this just feeds its
  // output through the shared `portalEdges` shape function.
  const portalAnchorEdges = useMemo(
    () => portalEdges(pairPortalAnchors(payload.rooms)),
    [payload.rooms]
  );

  const reactFlowPortalEdges = useMemo(
    () =>
      portalAnchorEdges.map((edge) => ({
        id: edge.id,
        source: String(edge.source),
        target: String(edge.target),
        label: edge.kindName,
        style: { strokeDasharray: '4 4' },
      })),
    [portalAnchorEdges]
  );

  const onPlaceRoom = useCallback(
    ({ roomId, grid_x, grid_y, floor: placedFloor }: PlaceRoomArgs) => {
      runAction(palette === 'story' ? 'story_place_room' : 'staff_place_room', {
        room_id: roomId,
        grid_x,
        grid_y,
        floor: placedFloor,
      });
    },
    [runAction, palette]
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
      edges={[...edges, ...reactFlowPortalEdges]}
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
