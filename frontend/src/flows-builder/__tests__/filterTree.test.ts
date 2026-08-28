/**
 * filterTree — pure tree ops / validation for the trigger filter-condition
 * DSL (#3417 task 12). Mirrors `src/flows/filters/evaluator.py` /
 * `src/flows/filters/validator.py`; see filterTree.ts's module docstring.
 */
import { describe, expect, it } from 'vitest';

import {
  addChild,
  changeOperator,
  childrenOf,
  emptyGroup,
  emptyLeaf,
  fromApiFilter,
  isAnd,
  isGroup,
  isLeaf,
  isNot,
  isOr,
  removeChild,
  setChild,
  setNotChild,
  toApiFilter,
  validateFilter,
  type FilterAnd,
  type FilterNode,
  type FilterNot,
  type FilterOr,
} from '../filterTree';

const OPS = ['==', '!=', '<', '<=', '>', '>=', 'in', 'contains'] as const;

function leaf(overrides: Partial<{ path: string; op: string; value: unknown }> = {}) {
  return { ...emptyLeaf(), path: 'actor', op: '==', value: 'self', ...overrides };
}

describe('type guards', () => {
  it('classifies leaves and each group shape', () => {
    const l = leaf();
    const and: FilterAnd = { and: [l] };
    const or: FilterOr = { or: [l] };
    const not: FilterNot = { not: l };

    expect(isLeaf(l)).toBe(true);
    expect(isAnd(and)).toBe(true);
    expect(isOr(or)).toBe(true);
    expect(isNot(not)).toBe(true);
    expect(isGroup(and)).toBe(true);
    expect(isGroup(or)).toBe(true);
    expect(isGroup(not)).toBe(true);
    expect(isGroup(l)).toBe(false);
  });
});

describe('group add/remove', () => {
  it('addChild appends a leaf to an AND group', () => {
    const group: FilterAnd = { and: [leaf({ path: 'a' })] };
    const next = addChild(group, leaf({ path: 'b' }));
    expect(isAnd(next)).toBe(true);
    expect((next as FilterAnd).and.map((c) => (isLeaf(c) ? c.path : null))).toEqual(['a', 'b']);
  });

  it('addChild defaults to a blank leaf when none is given', () => {
    const group: FilterOr = { or: [] };
    const next = addChild(group);
    expect((next as FilterOr).or).toEqual([emptyLeaf()]);
  });

  it('addChild appends to an OR group', () => {
    const group: FilterOr = { or: [leaf({ path: 'a' })] };
    const next = addChild(group, leaf({ path: 'b' }));
    expect((next as FilterOr).or).toHaveLength(2);
  });

  it('removeChild drops the child at the given index from AND', () => {
    const group: FilterAnd = { and: [leaf({ path: 'a' }), leaf({ path: 'b' }), leaf({ path: 'c' })] };
    const next = removeChild(group, 1);
    expect((next as FilterAnd).and.map((c) => (isLeaf(c) ? c.path : null))).toEqual(['a', 'c']);
  });

  it('removeChild drops the child at the given index from OR', () => {
    const group: FilterOr = { or: [leaf({ path: 'a' }), leaf({ path: 'b' })] };
    const next = removeChild(group, 0);
    expect((next as FilterOr).or.map((c) => (isLeaf(c) ? c.path : null))).toEqual(['b']);
  });

  it('setChild replaces the child at the given index without touching others', () => {
    const group: FilterAnd = { and: [leaf({ path: 'a' }), leaf({ path: 'b' })] };
    const next = setChild(group, 1, leaf({ path: 'replaced' }));
    expect((next as FilterAnd).and.map((c) => (isLeaf(c) ? c.path : null))).toEqual([
      'a',
      'replaced',
    ]);
  });

  it('childrenOf reads AND/OR arrays and wraps a NOT operand as a one-element array', () => {
    expect(childrenOf({ and: [leaf({ path: 'a' })] })).toEqual([leaf({ path: 'a' })]);
    expect(childrenOf({ or: [leaf({ path: 'a' })] })).toEqual([leaf({ path: 'a' })]);
    expect(childrenOf({ not: leaf({ path: 'a' }) })).toEqual([leaf({ path: 'a' })]);
  });

  it('mutations never mutate the input (return new arrays/objects)', () => {
    const original: FilterAnd = { and: [leaf({ path: 'a' })] };
    const snapshot = JSON.parse(JSON.stringify(original));
    addChild(original, leaf({ path: 'b' }));
    removeChild(original, 0);
    expect(original).toEqual(snapshot);
  });
});

describe('NOT arity', () => {
  it('converting AND -> NOT keeps only the first child', () => {
    const group: FilterAnd = { and: [leaf({ path: 'a' }), leaf({ path: 'b' }), leaf({ path: 'c' })] };
    const next = changeOperator(group, 'not');
    expect(isNot(next)).toBe(true);
    expect((next as FilterNot).not).toEqual(leaf({ path: 'a' }));
  });

  it('converting OR -> NOT keeps only the first child', () => {
    const group: FilterOr = { or: [leaf({ path: 'x' }), leaf({ path: 'y' })] };
    const next = changeOperator(group, 'not');
    expect((next as FilterNot).not).toEqual(leaf({ path: 'x' }));
  });

  it('converting an empty AND -> NOT falls back to a blank leaf (never an undefined operand)', () => {
    const group: FilterAnd = { and: [] };
    const next = changeOperator(group, 'not');
    expect((next as FilterNot).not).toEqual(emptyLeaf());
  });

  it('converting NOT -> AND wraps the single operand in a one-element list', () => {
    const not: FilterNot = { not: leaf({ path: 'a' }) };
    const next = changeOperator(not, 'and');
    expect((next as FilterAnd).and).toEqual([leaf({ path: 'a' })]);
  });

  it('converting NOT -> OR wraps the single operand in a one-element list', () => {
    const not: FilterNot = { not: leaf({ path: 'a' }) };
    const next = changeOperator(not, 'or');
    expect((next as FilterOr).or).toEqual([leaf({ path: 'a' })]);
  });

  it('setNotChild replaces the single operand', () => {
    const not: FilterNot = { not: leaf({ path: 'a' }) };
    const next = setNotChild(not, leaf({ path: 'b' }));
    expect(next.not).toEqual(leaf({ path: 'b' }));
  });

  it('emptyGroup builds a blank AND or OR group', () => {
    expect(emptyGroup('and')).toEqual({ and: [] });
    expect(emptyGroup('or')).toEqual({ or: [] });
  });
});

describe('leaf validation', () => {
  it('a null filter is always valid', () => {
    expect(validateFilter(null, OPS)).toEqual([]);
  });

  it('a well-formed leaf with a catalog op is valid', () => {
    expect(validateFilter(leaf(), OPS)).toEqual([]);
  });

  it('flags an empty path', () => {
    const errors = validateFilter(leaf({ path: '' }), OPS);
    expect(errors).toContainEqual(expect.stringContaining('path must be set'));
  });

  it('flags a whitespace-only path as empty', () => {
    const errors = validateFilter(leaf({ path: '   ' }), OPS);
    expect(errors).toContainEqual(expect.stringContaining('path must be set'));
  });

  it('flags an empty operator', () => {
    const errors = validateFilter(leaf({ op: '' }), OPS);
    expect(errors).toContainEqual(expect.stringContaining('operator must be picked'));
  });

  it('flags an operator not in the catalog', () => {
    const errors = validateFilter(leaf({ op: 'nonexistent_op' }), OPS);
    expect(errors).toContainEqual(expect.stringContaining("unknown operator 'nonexistent_op'"));
  });

  it('accepts self.* and deep dotted paths without extra checks (server-side-only validation)', () => {
    expect(validateFilter(leaf({ path: 'self.stats.willpower' }), OPS)).toEqual([]);
    expect(validateFilter(leaf({ path: 'actor.sheet.level' }), OPS)).toEqual([]);
  });

  it('collects every problem across a nested AND/OR/NOT tree, not just the first', () => {
    const tree: FilterNode = {
      and: [
        leaf({ path: '' }),
        { or: [leaf({ op: 'bogus' }), leaf()] },
        { not: leaf({ path: '', op: '' }) },
      ],
    };
    const errors = validateFilter(tree, OPS);
    expect(errors).toHaveLength(4);
    expect(errors.some((e) => e.includes('root.and[0]'))).toBe(true);
    expect(errors.some((e) => e.includes('root.and[1].or[0]'))).toBe(true);
    expect(errors.some((e) => e.includes('root.and[2].not'))).toBe(true);
  });
});

describe('serialization passthrough', () => {
  it('toApiFilter passes a leaf through unchanged', () => {
    const node = leaf({ path: 'self.name', op: 'in', value: ['a', 'b'] });
    expect(toApiFilter(node)).toEqual(node);
  });

  it('toApiFilter passes null through unchanged', () => {
    expect(toApiFilter(null)).toBeNull();
  });

  it('toApiFilter passes a nested group through unchanged', () => {
    const node: FilterNode = { and: [leaf(), { not: leaf({ path: 'b' }) }] };
    expect(toApiFilter(node)).toEqual(node);
  });

  it('fromApiFilter maps null and undefined server values to null', () => {
    expect(fromApiFilter(null)).toBeNull();
    expect(fromApiFilter(undefined)).toBeNull();
  });

  it('fromApiFilter passes a populated server value through unchanged', () => {
    const wire = { path: 'self.stat', op: '>=', value: 5 };
    expect(fromApiFilter(wire)).toEqual(wire);
  });

  it('round-trips a tree through toApiFilter -> fromApiFilter', () => {
    const node: FilterNode = { or: [leaf({ path: 'a' }), leaf({ path: 'b', value: 3 })] };
    expect(fromApiFilter(toApiFilter(node))).toEqual(node);
  });
});
