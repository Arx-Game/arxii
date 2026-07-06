/**
 * BattleMapCanvas — the strategic battle map (#2009): places positioned on
 * their plane coordinates, sized by footprint_radius, ringed by controlling
 * side. Read-only: `nodesDraggable={false}` (Decision 1 — reposition is a
 * future move action, #1712 explicitly did not build it). Clicking a place
 * selects it for the detail panel.
 *
 * Composition mirrors `buildings/components/BuilderCanvas.tsx`:
 * `ReactFlowProvider` wrapper, module-level `nodeTypes`, `Background` +
 * `Controls`.
 */

import { useCallback, useEffect, useMemo } from 'react';
import {
  Background,
  Controls,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
} from '@xyflow/react';

import { computeBounds, planeToCanvas, radiusToPixels } from '../mapMath';
import type { BattleDetail } from '../types';
import type { PlaceControlRole, PlaceNodeData } from './PlaceNode';
import { PlaceNode } from './PlaceNode';

import '@xyflow/react/dist/style.css';

const nodeTypes = { place: PlaceNode };

export interface BattleMapCanvasProps {
  detail: BattleDetail;
  selectedPlaceId: number | null;
  onSelectPlace: (placeId: number) => void;
}

export function BattleMapCanvas(props: BattleMapCanvasProps) {
  return (
    <ReactFlowProvider>
      <BattleMapCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function BattleMapCanvasInner({ detail, selectedPlaceId, onSelectPlace }: BattleMapCanvasProps) {
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

      const data: PlaceNodeData = {
        place,
        role,
        unitCount,
        pcCount,
        sizePx: radiusToPixels(place.footprint_radius, bounds),
        selected: place.id === selectedPlaceId,
        onSelect: onSelectPlace,
      };

      return {
        id: String(place.id),
        type: 'place',
        position: planeToCanvas(place, bounds),
        data,
        draggable: false,
      } satisfies Node;
    });
  }, [detail, selectedPlaceId, onSelectPlace]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);

  useEffect(() => {
    setNodes(computedNodes);
  }, [computedNodes, setNodes]);

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const placeId = Number(node.id);
      if (!Number.isNaN(placeId)) {
        onSelectPlace(placeId);
      }
    },
    [onSelectPlace]
  );

  if (detail.places.length === 0) {
    return (
      <div
        className="flex h-full w-full items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground"
        data-testid="battle-map-canvas-empty"
      >
        No places recorded for this battle yet.
      </div>
    );
  }

  return (
    <div className="h-full w-full" data-testid="battle-map-canvas">
      <ReactFlow
        nodes={nodes}
        edges={[]}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        nodesDraggable={false}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
