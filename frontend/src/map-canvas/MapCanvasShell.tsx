/**
 * MapCanvasShell — the React Flow chrome shared by the building builder
 * canvas (#670), the battle map canvas (#2009), and the world-builder canvas
 * (#2449): the `ReactFlowProvider` wrapper, the `<ReactFlow>` element, and
 * its `<Background>`/`<Controls>` children. Consumers own their own node/edge
 * computation (useMemo over domain data) and drag/click handlers; this only
 * owns the React Flow wiring and wrapper markup.
 */

import type { MouseEvent, ReactNode, TouchEvent } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeTypes,
  type OnNodesChange,
} from '@xyflow/react';

import '@xyflow/react/dist/style.css';

export interface MapCanvasShellProps {
  /** data-testid on the outer wrapper div. */
  testId: string;
  nodeTypes: NodeTypes;
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onNodeClick?: (event: MouseEvent, node: Node) => void;
  onNodeDragStop?: (event: MouseEvent | TouchEvent, node: Node) => void;
  onEdgeClick?: (event: MouseEvent, edge: Edge) => void;
  nodesDraggable?: boolean;
  snapToGrid?: boolean;
  snapGrid?: [number, number];
  /** Background grid gap in px; omit for React Flow's default dotted background. */
  backgroundGap?: number;
  fitView?: boolean;
  /**
   * Rendered instead of the map when there's nothing to show (e.g. a battle
   * with no recorded places) — skips mounting ReactFlow with an empty node
   * set. Owns its own wrapper markup/data-testid.
   */
  emptyState?: ReactNode;
}

export function MapCanvasShell({
  testId,
  nodeTypes,
  nodes,
  edges,
  onNodesChange,
  onNodeClick,
  onNodeDragStop,
  onEdgeClick,
  nodesDraggable,
  snapToGrid,
  snapGrid,
  backgroundGap,
  fitView = true,
  emptyState,
}: MapCanvasShellProps) {
  if (emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div className="h-full w-full" data-testid={testId}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={onNodeClick}
          onNodeDragStop={onNodeDragStop}
          onEdgeClick={onEdgeClick}
          nodesDraggable={nodesDraggable}
          snapToGrid={snapToGrid}
          snapGrid={snapGrid}
          fitView={fitView}
        >
          <Background gap={backgroundGap} />
          <Controls />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
