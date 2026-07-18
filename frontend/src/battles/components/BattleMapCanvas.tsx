/**
 * BattleMapCanvas — the strategic battle map (#2009): places positioned on
 * their plane coordinates, sized by footprint_radius, ringed by controlling
 * side. Read-only: `nodesDraggable={false}` (Decision 1 — reposition is a
 * future move action, #1712 explicitly did not build it). Clicking a place
 * selects it for the detail panel.
 *
 * Composition shares `@/map-canvas/MapCanvasShell` with
 * `buildings/components/BuilderCanvas.tsx`: `ReactFlowProvider` wrapper,
 * module-level `nodeTypes`, `Background` + `Controls`.
 */

import { useCallback, useMemo } from 'react';
import type { Node, NodeChange } from '@xyflow/react';

import {
  centeredNodePosition,
  computeBounds,
  planeToCanvas,
  radiusToPixels,
} from '@/map-canvas/coords';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';

import type { BattleDetail } from '../types';
import type { PlaceControlRole, PlaceNodeData } from './PlaceNode';
import { MIN_SIZE_PX, PlaceNode } from './PlaceNode';

const nodeTypes = { place: PlaceNode };

export interface BattleMapCanvasProps {
  detail: BattleDetail;
  selectedPlaceId: number | null;
  onSelectPlace: (placeId: number) => void;
}

export function BattleMapCanvas({ detail, selectedPlaceId, onSelectPlace }: BattleMapCanvasProps) {
  const computedNodes = useMemo<Node[]>(() => {
    const { places, sides, units, participants } = detail;
    const bounds = computeBounds(places);
    const roleBySideId = new Map(sides.map((side) => [side.id, side.role ?? null]));

    return places.map((place) => {
      const unitCount = units.filter((unit) => unit.place_id === place.id).length;
      const pcCount = participants.filter(
        (participant) => participant.place_id === place.id
      ).length;
      const rawRole =
        place.controlled_by_id != null ? (roleBySideId.get(place.controlled_by_id) ?? null) : null;
      const role: PlaceControlRole =
        rawRole === 'attacker' || rawRole === 'defender' ? rawRole : null;
      // Final rendered diameter, clamped so tiny footprints stay clickable —
      // computed once here so both the node's size and its centered position
      // (below) agree on the same value.
      const sizePx = Math.max(
        MIN_SIZE_PX,
        Math.round(radiusToPixels(place.footprint_radius, bounds) * 2)
      );

      const data: PlaceNodeData = {
        place,
        role,
        unitCount,
        pcCount,
        sizePx,
        selected: place.id === selectedPlaceId,
        onSelect: onSelectPlace,
      };

      return {
        id: String(place.id),
        type: 'place',
        // React Flow positions nodes by top-left corner — offset by half the
        // node's size so it's centered on the place's plane coordinate (#2009 review).
        position: centeredNodePosition(planeToCanvas(place, bounds), sizePx),
        data,
        draggable: false,
      } satisfies Node;
    });
  }, [detail, selectedPlaceId, onSelectPlace]);

  // Places never move interactively (read-only map — `nodesDraggable={false}`
  // below, Decision 1 in the header doc), so there's no mutable node state to
  // own: `computedNodes` is passed straight through as a controlled prop
  // (`areas/components/TacticalMap.tsx`'s memo-direct pattern), which also
  // fixes first paint — a `useNodesState([])` seed + mirroring `useEffect`
  // rendered an empty canvas for one frame before the effect caught up
  // (#2423). `MapCanvasShell.onNodesChange` is a required prop, so this is a
  // no-op: React Flow's internal dimension/selection bookkeeping (used for
  // its own measurement pass) doesn't need to round-trip back into our node
  // list, since selection here is driven by `selectedPlaceId` and dragging
  // is disabled.
  const onNodesChange = useCallback((_changes: NodeChange[]) => {}, []);

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const placeId = Number(node.id);
      if (!Number.isNaN(placeId)) {
        onSelectPlace(placeId);
      }
    },
    [onSelectPlace]
  );

  return (
    <MapCanvasShell
      testId="battle-map-canvas"
      nodes={computedNodes}
      edges={[]}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={onNodeClick}
      nodesDraggable={false}
      emptyState={
        detail.places.length === 0 ? (
          <div
            className="flex h-full w-full items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground"
            data-testid="battle-map-canvas-empty"
          >
            No places recorded for this battle yet.
          </div>
        ) : undefined
      }
    />
  );
}
