/**
 * Unit tests for the isTargetReachable helper (#532).
 *
 * Covers every branch of the reach pre-filter logic.
 */

import { describe, it, expect } from 'vitest';
import { isTargetReachable } from '../reach';
import type { PositionAdjacencyItem } from '../types';

// A simple two-position adjacency graph: position 1 ↔ position 2,
// and a disconnected position 3.
const adjacency: PositionAdjacencyItem[] = [
  { position_id: 1, adjacent_position_ids: [2] },
  { position_id: 2, adjacent_position_ids: [1] },
  { position_id: 3, adjacent_position_ids: [] },
];

describe('isTargetReachable — no constraint', () => {
  it('returns true when reach is null', () => {
    expect(isTargetReachable(null, 1, 3, adjacency)).toBe(true);
  });

  it('returns true when reach is undefined', () => {
    expect(isTargetReachable(undefined, 1, 3, adjacency)).toBe(true);
  });

  it('returns true when reach is "any"', () => {
    expect(isTargetReachable('any', 1, 3, adjacency)).toBe(true);
  });
});

describe('isTargetReachable — unplaced combatants (lenient)', () => {
  it('returns true when actor position is null (unplaced actor)', () => {
    expect(isTargetReachable('same', null, 2, adjacency)).toBe(true);
  });

  it('returns true when target position is null (unplaced target)', () => {
    expect(isTargetReachable('same', 1, null, adjacency)).toBe(true);
  });

  it('returns true when both positions are null', () => {
    expect(isTargetReachable('same', null, null, adjacency)).toBe(true);
  });

  it('returns true for undefined actor position', () => {
    expect(isTargetReachable('adjacent', undefined, 3, adjacency)).toBe(true);
  });

  it('returns true for undefined target position', () => {
    expect(isTargetReachable('adjacent', 1, undefined, adjacency)).toBe(true);
  });
});

describe('isTargetReachable — reach "same"', () => {
  it('returns true when actor and target share a position', () => {
    expect(isTargetReachable('same', 1, 1, adjacency)).toBe(true);
  });

  it('returns false when actor and target are in different positions', () => {
    expect(isTargetReachable('same', 1, 2, adjacency)).toBe(false);
  });

  it('returns false even if the positions are adjacent', () => {
    expect(isTargetReachable('same', 1, 2, adjacency)).toBe(false);
  });

  it('returns false for a completely disconnected position', () => {
    expect(isTargetReachable('same', 1, 3, adjacency)).toBe(false);
  });
});

describe('isTargetReachable — reach "adjacent"', () => {
  it('returns true when actor and target share a position (same counts as adjacent)', () => {
    expect(isTargetReachable('adjacent', 1, 1, adjacency)).toBe(true);
  });

  it('returns true when target is a direct adjacency-graph neighbour', () => {
    expect(isTargetReachable('adjacent', 1, 2, adjacency)).toBe(true);
  });

  it('returns true from the other direction of the edge', () => {
    expect(isTargetReachable('adjacent', 2, 1, adjacency)).toBe(true);
  });

  it('returns false when target is not adjacent and not the same position', () => {
    expect(isTargetReachable('adjacent', 1, 3, adjacency)).toBe(false);
  });

  it('returns false when actor has no adjacency entry and positions differ', () => {
    // position 3 has no neighbours in the graph above.
    expect(isTargetReachable('adjacent', 3, 1, adjacency)).toBe(false);
  });

  it('returns false when adjacency array is empty and positions differ', () => {
    expect(isTargetReachable('adjacent', 1, 2, [])).toBe(false);
  });
});

describe('isTargetReachable — unknown reach values', () => {
  it('defaults to true for unrecognised reach strings (lenient)', () => {
    expect(isTargetReachable('melee', 1, 3, adjacency)).toBe(true);
  });
});
