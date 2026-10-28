/**
 * MissionCanvas - graph visualization of a MissionTemplate's nodes + routes.
 *
 * Uses @xyflow/react for the canvas and dagre for auto-layout when a node
 * lacks stored editor_x/y. Dragging a node PATCHes editor_x/y back so the
 * position persists across sessions; clicking a node opens its page.
 *
 * Every way a mission can move on is drawn: tiered routes, random-set
 * candidates (dashed), branch targets, and track success/failure targets.
 * Anything that ends the mission points at one synthetic "Mission ends"
 * box, which exists only while something ends the mission and is never
 * saved. A node with a problem from the graph check gets a warning border.
 */

import { useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  Position,
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
  useGraphCheck,
  useMissionNodes,
  useMissionOptions,
  useMissionRouteCandidates,
  useMissionRoutes,
  useOutcomeTiers,
  usePatchMissionNode,
} from '../queries';
import { optionLabel } from '../optionLabel';
import type { StudioPaths } from '../studioPaths';
import type {
  GraphProblem,
  MissionNode,
  MissionOption,
  MissionOptionRoute,
  MissionOptionRouteCandidate,
  OutcomeTier,
} from '../types';

import '@xyflow/react/dist/style.css';

interface MissionCanvasProps {
  /** Template primary key (needed for the nodes-by-template filter). */
  templateId: number | undefined;
  /** Link builder for the current Studio mount; node clicks navigate with it. */
  paths: StudioPaths;
}

const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;

/** Id of the synthetic node every mission-ending edge points at. */
export const END_NODE_ID = 'end';
const END_LABEL = 'Mission ends';
const WARNING_BORDER = '2px solid hsl(var(--warning, 38 92% 50%))';

function nodeBorder(warned: boolean, isEntry: boolean): string | undefined {
  if (warned) return WARNING_BORDER;
  return isEntry ? '2px solid hsl(var(--primary))' : undefined;
}

export function MissionCanvas({ templateId, paths }: MissionCanvasProps) {
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
      <MissionCanvasInner templateId={templateId} paths={paths} />
    </ReactFlowProvider>
  );
}

function MissionCanvasInner({ templateId, paths }: { templateId: number; paths: StudioPaths }) {
  const nodesQuery = useMissionNodes({ template: templateId });
  const optionsQuery = useMissionOptions({ template: templateId });
  const routesQuery = useMissionRoutes({ template: templateId });
  const candidatesQuery = useMissionRouteCandidates({ template: templateId });
  const tiersQuery = useOutcomeTiers();
  const problemsQuery = useGraphCheck(templateId);
  const navigate = useNavigate();

  const isLoading =
    nodesQuery.isLoading ||
    optionsQuery.isLoading ||
    routesQuery.isLoading ||
    candidatesQuery.isLoading ||
    tiersQuery.isLoading;

  const { layoutedNodes, layoutedEdges } = useMemo(
    () =>
      computeLayout(
        nodesQuery.data?.results ?? [],
        optionsQuery.data?.results ?? [],
        routesQuery.data?.results ?? [],
        candidatesQuery.data?.results ?? [],
        tiersQuery.data ?? [],
        problemsQuery.data ?? []
      ),
    [
      nodesQuery.data,
      optionsQuery.data,
      routesQuery.data,
      candidatesQuery.data,
      tiersQuery.data,
      problemsQuery.data,
    ]
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
      // The synthetic "Mission ends" box has no row to save a position to.
      if (node.id === END_NODE_ID) return;
      const id = Number(node.id);
      if (Number.isNaN(id)) return;
      patchNode.mutate({
        id,
        body: { editor_x: Math.round(node.position.x), editor_y: Math.round(node.position.y) },
      });
    },
    [patchNode]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (node.id === END_NODE_ID) return;
      const id = Number(node.id);
      if (Number.isNaN(id)) return;
      navigate(paths.node(id));
    },
    [navigate, paths]
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
        onNodeClick={onNodeClick}
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

interface EdgeSpec {
  id: string;
  source: number;
  target: number | typeof END_NODE_ID;
  label: string;
  dashed?: boolean;
}

/** Options whose routes are optional: with no way on they simply end the mission. */
const ENDS_WITHOUT_ROUTE = new Set(['branch', 'external_act']);
/** Options that roll a check; on a track node the track, not a route, decides. */
const ROLLED_KINDS = new Set(['check', 'contest']);

function appendRandomRouteEdges(
  specs: EdgeSpec[],
  route: MissionOptionRoute,
  opt: MissionOption,
  candidates: readonly MissionOptionRouteCandidate[],
  routeLabel: string
): void {
  const drawn = candidates.filter((candidate) => candidate.route === route.id);
  for (const candidate of drawn) {
    specs.push({
      id: `c${candidate.id}`,
      source: opt.node,
      target: candidate.target_node,
      label: `${routeLabel} · random`,
      dashed: true,
    });
  }
  if (drawn.length === 0) {
    specs.push({ id: `r${route.id}`, source: opt.node, target: END_NODE_ID, label: routeLabel });
  }
}

function appendRouteEdges(
  route: MissionOptionRoute,
  optionMap: Map<number, MissionOption>,
  trackNodes: Set<number>,
  tierNames: Map<number, string>,
  candidates: readonly MissionOptionRouteCandidate[],
  specs: EdgeSpec[],
  tierlessByOption: Set<number>
): void {
  const opt = optionMap.get(route.option);
  if (!opt) return;
  const label = optionLabel(opt);
  const tierless = route.outcome_tier === null || route.outcome_tier === undefined;
  if (tierless) tierlessByOption.add(opt.id);
  // Branch routes and counted track rolls follow the same rules as the engine.
  if (!tierless && ENDS_WITHOUT_ROUTE.has(opt.option_kind)) return;
  if (ROLLED_KINDS.has(opt.option_kind) && trackNodes.has(opt.node)) return;
  if (tierless && opt.branch_target) return;
  const tierName = tierless ? null : tierNames.get(route.outcome_tier as number);
  const routeLabel = tierName ? `${label} · ${tierName}` : label;
  if (route.is_random_set) {
    appendRandomRouteEdges(specs, route, opt, candidates, routeLabel);
    return;
  }
  specs.push({
    id: `r${route.id}`,
    source: opt.node,
    target: route.target_node ?? END_NODE_ID,
    label: routeLabel,
  });
}

function collectEdges(
  rawNodes: readonly MissionNode[],
  rawOptions: readonly MissionOption[],
  rawRoutes: readonly MissionOptionRoute[],
  candidates: readonly MissionOptionRouteCandidate[],
  tiers: readonly OutcomeTier[]
): EdgeSpec[] {
  const optionMap = new Map(rawOptions.map((option) => [option.id, option]));
  const trackNodes = new Set(
    rawNodes.filter((node) => (node.track_successes ?? 0) > 0).map((node) => node.id)
  );
  const tierNames = new Map(tiers.map((tier) => [tier.id, tier.name]));

  const specs: EdgeSpec[] = [];
  const tierlessByOption = new Set<number>();

  for (const route of rawRoutes) {
    appendRouteEdges(route, optionMap, trackNodes, tierNames, candidates, specs, tierlessByOption);
  }

  for (const opt of rawOptions) {
    if (opt.branch_target) {
      specs.push({
        id: `b${opt.id}`,
        source: opt.node,
        target: opt.branch_target,
        label: optionLabel(opt),
      });
    } else if (ENDS_WITHOUT_ROUTE.has(opt.option_kind) && !tierlessByOption.has(opt.id)) {
      specs.push({
        id: `e${opt.id}`,
        source: opt.node,
        target: END_NODE_ID,
        label: optionLabel(opt),
      });
    }
  }

  for (const n of rawNodes) {
    // A track with no target for a side ends the mission on that side.
    const tracked = (n.track_successes ?? 0) > 0;
    if (n.track_success_target || tracked) {
      specs.push({
        id: `ts${n.id}`,
        source: n.id,
        target: n.track_success_target ?? END_NODE_ID,
        label: 'track success',
      });
    }
    if (n.track_failure_target || tracked) {
      specs.push({
        id: `tf${n.id}`,
        source: n.id,
        target: n.track_failure_target ?? END_NODE_ID,
        label: 'track failure',
      });
    }
  }
  return specs;
}

const LABEL_SEPARATOR = ' · ';
const COLUMN_GAP = 420;
const MAX_LABEL_LENGTH = 80;

/**
 * One arrow per (source, target, style): a check option's five routes into the same
 * node draw as one arrow labelled with every tier, not five stacked arrows whose labels
 * overprint. Labels sharing an option keep it once ("pick · Failure, Success").
 */
function mergeParallel(specs: readonly EdgeSpec[]): EdgeSpec[] {
  const groups = new Map<string, EdgeSpec[]>();
  for (const e of specs) {
    const key = `${e.source}>${e.target}>${e.dashed ? 'd' : 's'}`;
    const group = groups.get(key);
    if (group) group.push(e);
    else groups.set(key, [e]);
  }
  return [...groups.values()].map((group) => {
    if (group.length === 1) return group[0];
    const byOption = new Map<string, string[]>();
    for (const e of group) {
      const cut = e.label.indexOf(LABEL_SEPARATOR);
      const option = cut === -1 ? e.label : e.label.slice(0, cut);
      const rest = cut === -1 ? '' : e.label.slice(cut + LABEL_SEPARATOR.length);
      const parts = byOption.get(option) ?? [];
      if (rest) parts.push(rest);
      byOption.set(option, parts);
    }
    const full = [...byOption.entries()]
      .map(([option, parts]) =>
        parts.length ? `${option}${LABEL_SEPARATOR}${parts.join(', ')}` : option
      )
      .join('; ');
    // Past a readable length the arrow says how many it carries; the option page lists them.
    const label =
      full.length <= MAX_LABEL_LENGTH
        ? full
        : `${byOption.size} ${byOption.size === 1 ? 'option' : 'options'}${LABEL_SEPARATOR}${group.length} routes`;
    return { ...group[0], label };
  });
}

/**
 * Build React Flow nodes + edges and apply dagre auto-layout to any
 * node without stored editor_x/y. Nodes with stored coords keep them;
 * un-positioned nodes get auto-placed.
 */
export function computeLayout(
  rawNodes: readonly MissionNode[],
  rawOptions: readonly MissionOption[],
  rawRoutes: readonly MissionOptionRoute[],
  candidates: readonly MissionOptionRouteCandidate[],
  tiers: readonly OutcomeTier[],
  problems: readonly GraphProblem[]
): LayoutResult {
  const specs = mergeParallel(collectEdges(rawNodes, rawOptions, rawRoutes, candidates, tiers));
  const hasEnd = specs.some((e) => e.target === END_NODE_ID);

  const g = new dagre.graphlib.Graph();
  // Columns sit far enough apart for an arrow label naming several tiers to fit between them.
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: COLUMN_GAP });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of rawNodes) {
    g.setNode(String(n.id), { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  if (hasEnd) g.setNode(END_NODE_ID, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of specs) g.setEdge(String(e.source), String(e.target));
  dagre.layout(g);

  const optionNode = new Map<number, number>();
  for (const opt of rawOptions) optionNode.set(opt.id, opt.node);
  const flagged = new Set<number>();
  for (const p of problems) {
    const nodeId = p.node ?? (p.option !== null ? optionNode.get(p.option) : undefined);
    if (nodeId !== undefined && nodeId !== null) flagged.add(nodeId);
  }

  const layoutedNodes: Node[] = rawNodes.map((n) => {
    const dagreNode = g.node(String(n.id));
    const useStored = n.editor_x !== 0 || n.editor_y !== 0;
    const x = useStored ? (n.editor_x ?? 0) : dagreNode.x - NODE_WIDTH / 2;
    const y = useStored ? (n.editor_y ?? 0) : dagreNode.y - NODE_HEIGHT / 2;
    const warned = flagged.has(n.id);
    return {
      id: String(n.id),
      position: { x, y },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label:
          (warned ? '⚠ ' : '') +
          n.key +
          (n.is_entry ? ' (entry)' : '') +
          ((n.track_successes ?? 0) > 0 ? ` [track ${n.track_successes}/${n.track_failures}]` : ''),
      },
      style: {
        width: NODE_WIDTH,
        background: n.is_entry ? 'hsl(var(--primary) / 0.15)' : undefined,
        border: nodeBorder(warned, Boolean(n.is_entry)),
      },
    };
  });

  if (hasEnd) {
    const endNode = g.node(END_NODE_ID);
    layoutedNodes.push({
      id: END_NODE_ID,
      position: { x: endNode.x - NODE_WIDTH / 2, y: endNode.y - NODE_HEIGHT / 2 },
      data: { label: END_LABEL },
      targetPosition: Position.Left,
      draggable: false,
      style: { width: NODE_WIDTH, borderStyle: 'dashed' },
    });
  }

  const layoutedEdges: Edge[] = specs.map((e) => ({
    id: e.id,
    source: String(e.source),
    target: String(e.target),
    label: e.label,
    labelBgPadding: [6, 3] as [number, number],
    labelBgStyle: { fill: 'hsl(var(--background))' },
    style: e.dashed ? { strokeDasharray: '6 4' } : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));

  return { layoutedNodes, layoutedEdges };
}
