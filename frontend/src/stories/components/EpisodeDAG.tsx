/**
 * EpisodeDAG — read-only DAG visualization of a story's episode graph.
 *
 * Uses @xyflow/react for the graph canvas and dagre for automatic
 * top-to-bottom layout. Episodes are nodes; Transitions are directed edges.
 *
 * Data sourcing:
 *  - Episodes: all episodes in the story (via EpisodeFilter story= param)
 *  - Transitions: all transitions whose source episode is in the story
 *    (via TransitionFilter story= param → source_episode__chapter__story_id)
 *
 * Interaction: read-only pan/zoom. Clicking a node calls onEpisodeClick
 * so the parent can open the EpisodeFormDialog for editing.
 *
 * Frontier transitions (target_episode === null) point to a shared
 * "Frontier" sink node rendered with a dashed border.
 */

import { useMemo } from 'react';
import { ReactFlow, Controls, Background, BackgroundVariant, MarkerType } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import dagre from 'dagre';
import '@xyflow/react/dist/style.css';

import { useEpisodeList, useTransitionList } from '../queries';
import type { EpisodeList, Transition } from '../types';
import type { EpisodeLike } from './EpisodeFormDialog';
import { EpisodeNode } from './EpisodeNode';
import type { EpisodeNodeData, EpisodeNodeType } from './EpisodeNode';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_WIDTH = 180;
const NODE_HEIGHT = 56;
const FRONTIER_NODE_ID = '__frontier__';
const FRONTIER_NODE_WIDTH = 90;
const FRONTIER_NODE_HEIGHT = 36;

// ---------------------------------------------------------------------------
// Node types map — stable reference outside component to avoid React Flow
// re-registering node types on every render.
// ---------------------------------------------------------------------------

const nodeTypes = { episodeNode: EpisodeNode };

// ---------------------------------------------------------------------------
// Dagre layout helper
// ---------------------------------------------------------------------------

interface LayoutResult {
  nodes: Node[];
  edges: Edge[];
}

function computeLayout(
  episodes: EpisodeList[],
  transitions: Transition[],
  chapterTitles: Map<string, string>,
  onEpisodeClick: (episode: EpisodeLike) => void
): LayoutResult {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60, marginx: 20, marginy: 20 });

  const hasFrontier = transitions.some((t) => t.target_episode == null);

  // Register nodes
  for (const ep of episodes) {
    g.setNode(String(ep.id), { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  if (hasFrontier) {
    g.setNode(FRONTIER_NODE_ID, { width: FRONTIER_NODE_WIDTH, height: FRONTIER_NODE_HEIGHT });
  }

  // Register edges (dagre needs these for ranking)
  for (const t of transitions) {
    const src = String(t.source_episode);
    const tgt = t.target_episode != null ? String(t.target_episode) : FRONTIER_NODE_ID;
    g.setEdge(src, tgt);
  }

  dagre.layout(g);

  // Build React Flow nodes
  const rfNodes: EpisodeNodeType[] = episodes.map((ep) => {
    const node = g.node(String(ep.id));
    const chLabel = chapterTitles.get(ep.chapter) ?? 'Ch?';
    const breadcrumb = `${chLabel} · Ep ${ep.order ?? ep.id}`;

    // EpisodeList lacks description; omit it — the edit form is pre-populated
    // from the server when the dialog opens.
    const episodeLike: EpisodeLike = {
      id: ep.id,
      title: ep.title,
      order: ep.order,
    };

    const nodeData: EpisodeNodeData = {
      breadcrumb,
      title: ep.title,
      episode: episodeLike,
      onEpisodeClick,
    };

    return {
      id: String(ep.id),
      type: 'episodeNode',
      position: { x: node.x - NODE_WIDTH / 2, y: node.y - NODE_HEIGHT / 2 },
      data: nodeData,
    };
  });

  if (hasFrontier) {
    const fNode = g.node(FRONTIER_NODE_ID);
    const frontierData: EpisodeNodeData = {
      breadcrumb: '',
      title: 'Frontier',
      isFrontier: true,
    };
    rfNodes.push({
      id: FRONTIER_NODE_ID,
      type: 'episodeNode',
      position: {
        x: fNode.x - FRONTIER_NODE_WIDTH / 2,
        y: fNode.y - FRONTIER_NODE_HEIGHT / 2,
      },
      data: frontierData,
    });
  }

  // Build React Flow edges
  const rfEdges: Edge[] = transitions.map((t) => {
    const src = String(t.source_episode);
    const tgt = t.target_episode != null ? String(t.target_episode) : FRONTIER_NODE_ID;
    const isFrontier = t.target_episode == null;
    const isGMChoice = t.mode === 'gm_choice';

    const connType = (t.connection_type as string | undefined) ?? '';
    const summary = t.connection_summary ?? '';
    const rawLabel = [connType.toUpperCase(), summary].filter(Boolean).join(': ');
    const label = rawLabel.length > 40 ? `${rawLabel.slice(0, 37)}…` : rawLabel;

    return {
      id: `e-${t.id}`,
      source: src,
      target: tgt,
      label: label || undefined,
      animated: false,
      style: {
        strokeDasharray: isGMChoice || isFrontier ? '6 3' : undefined,
        stroke: isFrontier ? 'hsl(var(--muted-foreground))' : 'hsl(var(--foreground))',
        strokeWidth: 1.5,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isFrontier ? 'hsl(var(--muted-foreground))' : 'hsl(var(--foreground))',
      },
      labelStyle: { fontSize: 10, fill: 'hsl(var(--muted-foreground))' },
      labelBgStyle: { fill: 'hsl(var(--background))', fillOpacity: 0.85 },
    } satisfies Edge;
  });

  return { nodes: rfNodes, edges: rfEdges };
}

// ---------------------------------------------------------------------------
// EpisodeDAG component
// ---------------------------------------------------------------------------

export interface EpisodeDAGProps {
  storyId: number;
  /** Called when the user clicks an episode node; receives EpisodeLike for dialog. */
  onEpisodeClick: (episode: EpisodeLike) => void;
}

export function EpisodeDAG({ storyId, onEpisodeClick }: EpisodeDAGProps) {
  // Fetch all episodes and transitions for the story in single requests.
  const { data: episodesData, isLoading: episodesLoading } = useEpisodeList({
    story: storyId,
    page_size: 500,
  });
  const { data: transitionsData, isLoading: transitionsLoading } = useTransitionList({
    story: storyId,
    page_size: 500,
  });

  // Stabilise array references: react-hooks/exhaustive-deps warns when
  // `data?.results ?? []` is used directly in useMemo deps because the
  // nullish-coalescing expression creates a new [] reference each render.
  const episodes = useMemo(() => episodesData?.results ?? [], [episodesData]);
  const transitions = useMemo(() => transitionsData?.results ?? [], [transitionsData]);

  // Derive an ordinal label per chapter from the order episodes appear.
  // EpisodeList.chapter is a string (DRF PK representation). We group by it
  // and assign Ch1/Ch2/... ordinal labels.
  const chapterTitles = useMemo<Map<string, string>>(() => {
    const seen: string[] = [];
    for (const ep of episodes) {
      if (!seen.includes(ep.chapter)) seen.push(ep.chapter);
    }
    const map = new Map<string, string>();
    seen.forEach((chId, idx) => map.set(chId, `Ch${idx + 1}`));
    return map;
  }, [episodes]);

  // Compute dagre layout — only recomputes when episodes/transitions change.
  const { nodes: rfNodes, edges: rfEdges } = useMemo(() => {
    if (episodes.length === 0) return { nodes: [], edges: [] };
    return computeLayout(episodes, transitions, chapterTitles, onEpisodeClick);
  }, [episodes, transitions, chapterTitles, onEpisodeClick]);

  const isLoading = episodesLoading || transitionsLoading;

  if (isLoading) {
    return (
      <div
        className="flex h-64 items-center justify-center text-sm text-muted-foreground"
        data-testid="dag-loading"
      >
        Loading graph…
      </div>
    );
  }

  if (episodes.length === 0) {
    return (
      <div
        className="flex h-64 items-center justify-center text-sm italic text-muted-foreground"
        data-testid="dag-empty"
      >
        No episodes yet. Add episodes in the Tree view to see the DAG.
      </div>
    );
  }

  return (
    <div
      className="relative h-[600px] w-full overflow-hidden rounded-md border border-border"
      data-testid="dag-canvas"
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.25}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
      >
        <Controls />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      </ReactFlow>
    </div>
  );
}
