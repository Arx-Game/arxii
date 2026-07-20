import { describe, expect, it } from 'vitest';

import { exitEdges, portalEdges, type ExitRecord, type PortalAnchorRecord } from './edges';

describe('exitEdges', () => {
  const exit = (id: number, name: string, from: number, to: number): ExitRecord => ({
    id,
    name,
    from_room_id: from,
    to_room_id: to,
  });

  it('pairs a two-way link into one edge', () => {
    const edges = exitEdges([exit(10, 'east', 1, 2), exit(11, 'west', 2, 1)]);
    expect(edges).toHaveLength(1);
    expect(edges[0].there?.name).toBe('east');
    expect(edges[0].back?.name).toBe('west');
  });

  it('keeps a one-way exit as an edge with a null back', () => {
    const edges = exitEdges([exit(10, 'chute', 3, 4)]);
    expect(edges).toHaveLength(1);
    expect(edges[0].there?.name).toBe('chute');
    expect(edges[0].back).toBeNull();
  });

  it('gives parallel pairs a stable id per room pair', () => {
    const edges = exitEdges([exit(10, 'east', 1, 2), exit(11, 'west', 2, 1)]);
    expect(edges[0].id).toBe('exit-1-2');
  });
});

describe('portalEdges', () => {
  it('builds one edge per portal anchor with a resolved destination', () => {
    const anchors: PortalAnchorRecord[] = [
      { id: 1, room_id: 10, kind_name: 'Mirror', destination_room_id: 20 },
    ];
    const edges = portalEdges(anchors);
    expect(edges).toEqual([{ id: 'portal-1', source: 10, target: 20, kindName: 'Mirror' }]);
  });

  it('omits anchors with no resolvable destination (e.g. sole/unpaired anchor)', () => {
    const anchors: PortalAnchorRecord[] = [
      { id: 1, room_id: 10, kind_name: 'Mirror', destination_room_id: null },
    ];
    expect(portalEdges(anchors)).toEqual([]);
  });
});
