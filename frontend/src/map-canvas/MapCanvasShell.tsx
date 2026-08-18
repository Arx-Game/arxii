/**
 * MapCanvasShell — the React Flow chrome shared by the building builder
 * canvas (#670), the battle map canvas (#2009), and the world-builder canvas
 * (#2449): the `ReactFlowProvider` wrapper, the `<ReactFlow>` element, and
 * its `<Background>`/`<Controls>` children. Consumers own their own node/edge
 * computation (useMemo over domain data) and drag/click handlers; this only
 * owns the React Flow wiring and wrapper markup.
 */

import { useEffect, useRef, type MouseEvent, type ReactNode, type TouchEvent } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
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
   * #3269 canvas-navigation opt-ins — all default to prior behavior so the
   * building and battle canvases are unaffected; WorldCanvas opts in.
   */
  /** Minimum zoom (ReactFlow default 0.5 clamps grid-scale zoom-out). */
  minZoom?: number;
  /** Render a MiniMap for orientation on large grids. */
  showMiniMap?: boolean;
  /**
   * Refit the viewport when this key changes (e.g. the sorted room-id set) —
   * deliberately NOT on every payload change, which would yank the viewport
   * after each rename/stat edit/drag-place.
   */
  refitKey?: string;
  /**
   * Rendered instead of the map when there's nothing to show (e.g. a battle
   * with no recorded places) — skips mounting ReactFlow with an empty node
   * set. Owns its own wrapper markup/data-testid.
   */
  emptyState?: ReactNode;
}

/**
 * Refit-on-key-change effect (#3269). Must be rendered INSIDE the
 * ReactFlowProvider — `useReactFlow` reads the provider's context, so the
 * shell component body itself cannot host this hook.
 */
function ViewportRefit({ refitKey }: { refitKey?: string }) {
  const reactFlow = useReactFlow();
  const previous = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (refitKey !== undefined && previous.current !== undefined && refitKey !== previous.current) {
      reactFlow.fitView();
    }
    previous.current = refitKey;
  }, [refitKey, reactFlow]);
  return null;
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
  minZoom,
  showMiniMap = false,
  refitKey,
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
          minZoom={minZoom}
        >
          <Background gap={backgroundGap} />
          <Controls />
          {showMiniMap && <MiniMap pannable zoomable />}
          <ViewportRefit refitKey={refitKey} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
