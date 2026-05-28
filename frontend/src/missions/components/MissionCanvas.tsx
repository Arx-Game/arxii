/**
 * MissionCanvas — graph visualization of a MissionTemplate's nodes + routes.
 *
 * Uses @xyflow/react for the canvas and dagre for auto-layout when a node
 * lacks stored editor_x/y. Dragging a node PATCHes editor_x/y back via
 * D2 (`patchMissionNode`) so the position persists across sessions.
 *
 * Scope (E2):
 * - Nodes as labeled boxes; entry node visually distinguished.
 * - Edges = (option, route) per node — labeled with outcome tier name.
 * - Random-set routes drawn as a single edge with the "random" label
 *   (per-candidate fan visualization deferred).
 * - The plan's "validation overlay" was contingent on a D2 `/validate/`
 *   action that didn't ship; deferred until that endpoint exists.
 */

import { useCallback, useEffect, useMemo } from 'react';
import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import dagre from 'dagre';

import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import {
  useMissionNodes,
  useMissionOptions,
  useMissionRoutes,
  usePatchMissionNode,
} from '../queries';
import type { MissionNode, MissionOption, MissionOptionRoute } from '../types';

import '@xyflow/react/dist/style.css';

interface MissionCanvasProps {
  /** Template primary key (needed for the nodes-by-template filter). */
  templateId: number | undefined;
  /** @deprecated No longer used — pass only templateId. Will be removed in a follow-up. */
  templateSlug?: string | undefined;
}

const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;

export function MissionCanvas({ templateId }: MissionCanvasProps) {
  if (!templateId) {
    return (
      <Card>
        <CardContent className="p-6 text-muted-foreground">
          Select a mission to view its graph.
        </CardContent>
      </Card>
    );
  }
  return (
    <ReactFlowProvider>
      <MissionCanvasInner templateId={templateId} />
    </ReactFlowProvider>
  );
}

function MissionCanvasInner({ templateId }: { templateId: number }) {
  const nodesQuery = useMissionNodes({ template: templateId });
  const optionsQuery = useMissionOptions({ template: templateId });
  const routesQuery = useMissionRoutes({ template: templateId });

  const isLoading = nodesQuery.isLoading || optionsQuery.isLoading || routesQuery.isLoading;

  const { layoutedNodes, layoutedEdges } = useMemo(
    () =>
      computeLayout(
        nodesQuery.data?.results ?? [],
        optionsQuery.data?.results ?? [],
        routesQuery.data?.results ?? []
      ),
    [nodesQuery.data, optionsQuery.data, routesQuery.data]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Replay layout when underlying data changes.
  useEffect(() => {
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [layoutedNodes, layoutedEdges, setNodes, setEdges]);

  const patchNode = usePatchMissionNode();

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent | React.TouchEvent, node: Node) => {
      const id = Number(node.id);
      if (Number.isNaN(id)) return;
      patchNode.mutate({
        id,
        body: { editor_x: Math.round(node.position.x), editor_y: Math.round(node.position.y) },
      });
    },
    [patchNode]
  );

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div data-testid="mission-canvas" className="h-[600px] w-full rounded border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        fitView
      >
        <Background gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
}

interface LayoutResult {
  layoutedNodes: Node[];
  layoutedEdges: Edge[];
}

/**
 * Build React Flow nodes + edges and apply dagre auto-layout to any
 * node without stored editor_x/y. Nodes with stored coords keep them;
 * un-positioned nodes get auto-placed.
 */
export function computeLayout(
  rawNodes: readonly MissionNode[],
  rawOptions: readonly MissionOption[],
  rawRoutes: readonly MissionOptionRoute[]
): LayoutResult {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 100 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of rawNodes) {
    g.setNode(String(n.id), { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  // Build option -> node lookup for edge construction.
  const optionToNode = new Map<number, number>();
  for (const opt of rawOptions) {
    optionToNode.set(opt.id, opt.node);
  }
  for (const route of rawRoutes) {
    const sourceNode = optionToNode.get(route.option);
    if (sourceNode === undefined || route.target_node === null || route.target_node === undefined) {
      continue;
    }
    g.setEdge(String(sourceNode), String(route.target_node));
  }
  dagre.layout(g);

  const layoutedNodes: Node[] = rawNodes.map((n) => {
    const dagreNode = g.node(String(n.id));
    const useStored = n.editor_x !== 0 || n.editor_y !== 0;
    const x = useStored ? (n.editor_x ?? 0) : dagreNode.x - NODE_WIDTH / 2;
    const y = useStored ? (n.editor_y ?? 0) : dagreNode.y - NODE_HEIGHT / 2;
    return {
      id: String(n.id),
      position: { x, y },
      data: { label: n.key + (n.is_entry ? ' (entry)' : '') },
      style: {
        width: NODE_WIDTH,
        background: n.is_entry ? 'hsl(var(--primary) / 0.15)' : undefined,
        border: n.is_entry ? '2px solid hsl(var(--primary))' : undefined,
      },
    };
  });

  // Build option -> outcome lookup (for edge labels).
  const optionMap = new Map<number, MissionOption>();
  for (const opt of rawOptions) optionMap.set(opt.id, opt);

  const layoutedEdges: Edge[] = rawRoutes
    .filter((r) => r.target_node !== null && r.target_node !== undefined)
    .map((r) => {
      const opt = optionMap.get(r.option);
      const source = opt ? opt.node : 0;
      const label = r.is_random_set
        ? 'random'
        : r.outcome_tier !== null && r.outcome_tier !== undefined
          ? `t${r.outcome_tier}`
          : 'branch';
      return {
        id: `r${r.id}`,
        source: String(source),
        target: String(r.target_node),
        label,
        markerEnd: { type: MarkerType.ArrowClosed },
      };
    });

  return { layoutedNodes, layoutedEdges };
}
