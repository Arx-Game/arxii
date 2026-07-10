/**
 * Pure layout math for the tactical map (#2006).
 *
 * When a node has authored layout_x/layout_y (both non-null), those cosmetic
 * coordinates are used verbatim. Otherwise a deterministic BFS-ring layout
 * places it: anchor = the PRIMARY-kind node (lowest-pk fallback), radius =
 * hop-distance from the anchor, spread evenly around the ring at that
 * radius. Nodes carrying elevation_anchor_id get an additional upward
 * (negative-y) offset, layered above their anchor — mirrors gridMath.ts's
 * north-is-negative-screen-y convention.
 */

export interface TacticalNode {
  id: number;
  kind: string;
  elevation_anchor_id: number | null;
  layout_x: number | null;
  layout_y: number | null;
}

export interface TacticalEdge {
  position_a_id: number;
  position_b_id: number;
}

export interface LayoutPoint {
  x: number;
  y: number;
}

export const RING_RADIUS = 160;
export const ELEVATION_OFFSET = 120;

function buildAdjacency(nodes: TacticalNode[], edges: TacticalEdge[]): Map<number, number[]> {
  const adjacency = new Map<number, number[]>(nodes.map((n) => [n.id, []]));
  for (const edge of edges) {
    adjacency.get(edge.position_a_id)?.push(edge.position_b_id);
    adjacency.get(edge.position_b_id)?.push(edge.position_a_id);
  }
  return adjacency;
}

function bfsHopDistances(anchorId: number, adjacency: Map<number, number[]>): Map<number, number> {
  const distances = new Map<number, number>([[anchorId, 0]]);
  const queue: number[] = [anchorId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const depth = distances.get(current)!;
    for (const neighbor of adjacency.get(current) ?? []) {
      if (!distances.has(neighbor)) {
        distances.set(neighbor, depth + 1);
        queue.push(neighbor);
      }
    }
  }
  return distances;
}

/** BFS-ring auto-layout: anchor = PRIMARY kind (lowest-pk fallback). */
function autoLayoutRing(nodes: TacticalNode[], edges: TacticalEdge[]): Map<number, LayoutPoint> {
  if (nodes.length === 0) return new Map();

  const sortedByPk = [...nodes].sort((a, b) => a.id - b.id);
  const anchor = sortedByPk.find((n) => n.kind === 'primary') ?? sortedByPk[0];
  const adjacency = buildAdjacency(nodes, edges);
  const distances = bfsHopDistances(anchor.id, adjacency);

  // Group by hop-distance. Disconnected nodes (not reached by BFS from the
  // anchor) are placed one ring beyond the farthest reached ring, so they
  // never overlap the anchor's own rings.
  const byRing = new Map<number, number[]>();
  let maxReachedRing = 0;
  for (const distance of distances.values()) {
    maxReachedRing = Math.max(maxReachedRing, distance);
  }
  for (const node of sortedByPk) {
    const ring = distances.get(node.id) ?? maxReachedRing + 1;
    const bucket = byRing.get(ring) ?? [];
    bucket.push(node.id);
    byRing.set(ring, bucket);
  }

  const points = new Map<number, LayoutPoint>();
  for (const [ring, ids] of byRing) {
    if (ring === 0) {
      points.set(ids[0], { x: 0, y: 0 });
      continue;
    }
    const radius = ring * RING_RADIUS;
    ids.forEach((id, index) => {
      const angle = (2 * Math.PI * index) / ids.length;
      points.set(id, {
        x: Math.round(radius * Math.cos(angle)),
        y: Math.round(radius * Math.sin(angle)),
      });
    });
  }
  return points;
}

/** Hop-count up the elevation_anchor chain (cycle-safe). */
function elevationDepth(node: TacticalNode, nodesById: Map<number, TacticalNode>): number {
  let depth = 0;
  let current: TacticalNode | undefined = node;
  const visited = new Set<number>();
  while (current?.elevation_anchor_id != null && !visited.has(current.id)) {
    visited.add(current.id);
    depth += 1;
    current = nodesById.get(current.elevation_anchor_id);
  }
  return depth;
}

/**
 * Compute canvas positions for every node: stored layout_x/layout_y when
 * both are non-null, else the BFS-ring auto-layout — then an elevation
 * y-offset on top for nodes with elevation_anchor_id set.
 */
export function computeTacticalLayout(
  nodes: TacticalNode[],
  edges: TacticalEdge[]
): Map<number, LayoutPoint> {
  const autoPoints = autoLayoutRing(nodes, edges);
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const result = new Map<number, LayoutPoint>();
  for (const node of nodes) {
    const base =
      node.layout_x !== null && node.layout_y !== null
        ? { x: node.layout_x, y: node.layout_y }
        : (autoPoints.get(node.id) ?? { x: 0, y: 0 });
    const depth = elevationDepth(node, nodesById);
    result.set(node.id, { x: base.x, y: base.y - depth * ELEVATION_OFFSET });
  }
  return result;
}
