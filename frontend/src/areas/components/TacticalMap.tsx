/**
 * TacticalMap — read-only React Flow rendering of a room's Position graph
 * (#2006): occupant avatars per node, edges styled by passability/gating,
 * click-to-move via the existing single-hop action picker.
 *
 * Reuses the @xyflow/react canvas idiom from BuilderCanvas (#670) but with
 * dragging disabled — coordinate authoring is out of scope for this issue.
 */

import { useMemo } from 'react';
import {
  Background,
  Controls,
  Position as FlowPosition,
  ReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import { toast } from 'sonner';

import type { PlayerAction } from '@/scenes/actionTypes';
import { computeTacticalLayout } from '../tacticalLayout';
import type { TacticalEdge, TacticalNode } from '../tacticalLayout';
import { PositionMapNode } from './PositionMapNode';
import type { OccupantSummary, PositionMapNodeType } from './PositionMapNode';

import '@xyflow/react/dist/style.css';

const nodeTypes = { position: PositionMapNode };

// Fallback size for PositionMapNode's rendered box, matched in
// PositionMapNode.tsx's `w-[140px]` class. Passed explicitly on every node
// below (with matching synthetic `handles`) so React Flow can compute edge
// endpoints immediately — without waiting on a `ResizeObserver` pass over the
// real DOM. This isn't just a test convenience: it's React Flow's documented
// mechanism for measurement-free rendering (see their SSR guide), and it
// avoids an initial-layout flash in real browsers too. Once a real
// measurement lands, React Flow's own `internals.handleBounds` takes over.
const NODE_WIDTH = 140;
const NODE_HEIGHT = 72;

function fallbackHandles() {
  return [
    { id: null, type: 'target' as const, position: FlowPosition.Top, x: NODE_WIDTH / 2, y: 0 },
    {
      id: null,
      type: 'source' as const,
      position: FlowPosition.Bottom,
      x: NODE_WIDTH / 2,
      y: NODE_HEIGHT,
    },
  ];
}

export interface PositionNodeLike extends TacticalNode {
  id: number;
  name: string;
}

export interface PositionEdgeLike extends TacticalEdge {
  is_passable: boolean;
  blocks_flight: boolean;
  gating_challenge_name: string | null;
}

export interface TacticalMapProps {
  nodes: PositionNodeLike[];
  edges: PositionEdgeLike[];
  occupantsByPosition: Map<number, OccupantSummary[]>;
  moveActions: PlayerAction[];
  onDispatchMove: (action: PlayerAction) => void;
}

function edgeStyle(edge: PositionEdgeLike): { style: React.CSSProperties; label?: string } {
  if (edge.gating_challenge_name) {
    return {
      style: { strokeDasharray: '4 4', stroke: 'var(--color-amber-500, #f59e0b)' },
      label: edge.gating_challenge_name,
    };
  }
  if (!edge.is_passable) {
    return { style: { strokeDasharray: '2 4', opacity: 0.4 } };
  }
  return { style: {} };
}

export function TacticalMap({
  nodes,
  edges,
  occupantsByPosition,
  moveActions,
  onDispatchMove,
}: TacticalMapProps) {
  const moveActionByPositionId = useMemo(() => {
    const map = new Map<number, PlayerAction>();
    for (const action of moveActions) {
      if (action.ref.position_id != null) {
        map.set(action.ref.position_id, action);
      }
    }
    return map;
  }, [moveActions]);

  const handleClick = (positionId: number) => {
    const action = moveActionByPositionId.get(positionId);
    if (action) {
      onDispatchMove(action);
      return;
    }
    toast.error("Can't move there — no open path from your current position.");
  };

  const layout = useMemo(() => computeTacticalLayout(nodes, edges), [nodes, edges]);

  const flowNodes: Node[] = useMemo(
    () =>
      nodes.map(
        (position): PositionMapNodeType => ({
          id: String(position.id),
          type: 'position',
          position: layout.get(position.id) ?? { x: 0, y: 0 },
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          handles: fallbackHandles(),
          draggable: false,
          selectable: false,
          data: {
            positionId: position.id,
            name: position.name,
            kind: position.kind,
            occupants: occupantsByPosition.get(position.id) ?? [],
            canMoveHere: moveActionByPositionId.has(position.id),
            onClick: handleClick,
          },
        })
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nodes, layout, occupantsByPosition, moveActionByPositionId]
  );

  const flowEdges: Edge[] = useMemo(
    () =>
      edges.map((edge, index) => {
        const { style, label } = edgeStyle(edge);
        return {
          id: `edge-${edge.position_a_id}-${edge.position_b_id}-${index}`,
          source: String(edge.position_a_id),
          target: String(edge.position_b_id),
          type: 'straight',
          style,
          label,
        };
      }),
    [edges]
  );

  return (
    <div className="h-full w-full" data-testid="tactical-map">
      <ReactFlowProvider>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          fitView
        >
          <Background gap={40} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
