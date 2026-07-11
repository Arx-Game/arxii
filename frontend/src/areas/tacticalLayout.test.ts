import { describe, expect, it } from 'vitest';

import { computeTacticalLayout, type TacticalEdge, type TacticalNode } from './tacticalLayout';

const node = (
  id: number,
  kind = 'feature',
  elevationAnchorId: number | null = null,
  layoutX: number | null = null,
  layoutY: number | null = null
): TacticalNode => ({
  id,
  kind,
  elevation_anchor_id: elevationAnchorId,
  layout_x: layoutX,
  layout_y: layoutY,
});

const edge = (a: number, b: number): TacticalEdge => ({
  position_a_id: a,
  position_b_id: b,
});

describe('computeTacticalLayout', () => {
  it('places the PRIMARY anchor at the origin', () => {
    const points = computeTacticalLayout([node(1, 'primary')], []);
    expect(points.get(1)).toEqual({ x: 0, y: 0 });
  });

  it('falls back to the lowest-pk node as anchor when no PRIMARY exists', () => {
    const nodes = [node(5, 'feature'), node(2, 'feature')];
    const points = computeTacticalLayout(nodes, [edge(2, 5)]);
    expect(points.get(2)).toEqual({ x: 0, y: 0 });
  });

  it('places a one-hop neighbor away from the origin', () => {
    const nodes = [node(1, 'primary'), node(2, 'feature')];
    const points = computeTacticalLayout(nodes, [edge(1, 2)]);
    const anchor = points.get(1)!;
    const neighbor = points.get(2)!;
    const distance = Math.hypot(neighbor.x - anchor.x, neighbor.y - anchor.y);
    expect(distance).toBeGreaterThan(0);
  });

  it('places two-hop nodes farther out than one-hop nodes', () => {
    const nodes = [node(1, 'primary'), node(2, 'feature'), node(3, 'feature')];
    const points = computeTacticalLayout(nodes, [edge(1, 2), edge(2, 3)]);
    const anchor = points.get(1)!;
    const oneHop = points.get(2)!;
    const twoHop = points.get(3)!;
    const oneHopDist = Math.hypot(oneHop.x - anchor.x, oneHop.y - anchor.y);
    const twoHopDist = Math.hypot(twoHop.x - anchor.x, twoHop.y - anchor.y);
    expect(twoHopDist).toBeGreaterThan(oneHopDist);
  });

  it('uses stored layout_x/layout_y verbatim when both are set', () => {
    const nodes = [node(1, 'primary', null, 42, -17)];
    const points = computeTacticalLayout(nodes, []);
    expect(points.get(1)).toEqual({ x: 42, y: -17 });
  });

  it('shifts an elevated node upward (negative y) relative to its anchor', () => {
    const nodes = [node(1, 'primary'), node(2, 'elevated', 1)];
    const points = computeTacticalLayout(nodes, [edge(1, 2)]);
    const anchorY = points.get(1)!.y;
    const elevatedY = points.get(2)!.y;
    expect(elevatedY).toBeLessThan(anchorY);
  });

  it('is deterministic across repeated calls with the same input', () => {
    const nodes = [node(1, 'primary'), node(2, 'feature'), node(3, 'feature')];
    const edges = [edge(1, 2), edge(2, 3)];
    const first = computeTacticalLayout(nodes, edges);
    const second = computeTacticalLayout(nodes, edges);
    expect([...first.entries()]).toEqual([...second.entries()]);
  });
});
