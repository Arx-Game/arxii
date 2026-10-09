/**
 * Which generation each person of a kin tree stands in (#2062, #3003, #4209).
 *
 * One rule, shared by the graph's layout (`KinTreeGraph`) and the family page's
 * roll, so the two never disagree about who is a parent and who a child.
 */
import type { KinspersonNode, ParentageEdge } from './types';

/**
 * One generation per node, derived by walking parentage depth from the roots
 * (no visible parent → generation 0; otherwise one below the deepest visible
 * parent). A cycle guard keeps this a total function over any edge set —
 * upstream data is never trusted blindly in a layout algorithm that must
 * always terminate.
 */
export function computeGenerations(
  nodes: KinspersonNode[],
  parentage: ParentageEdge[]
): Map<number, number> {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const parentsOf = new Map<number, number[]>();
  for (const edge of parentage) {
    if (!nodeIds.has(edge.child_id) || !nodeIds.has(edge.parent_id)) continue;
    const list = parentsOf.get(edge.child_id) ?? [];
    list.push(edge.parent_id);
    parentsOf.set(edge.child_id, list);
  }

  const generation = new Map<number, number>();
  const visiting = new Set<number>();

  function resolve(id: number): number {
    const cached = generation.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) {
      generation.set(id, 0);
      return 0;
    }
    visiting.add(id);
    const parents = parentsOf.get(id) ?? [];
    const gen = parents.length === 0 ? 0 : Math.max(...parents.map(resolve)) + 1;
    visiting.delete(id);
    generation.set(id, gen);
    return gen;
  }

  for (const node of nodes) resolve(node.id);
  return generation;
}
