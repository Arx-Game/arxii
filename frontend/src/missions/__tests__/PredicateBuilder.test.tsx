/**
 * PredicateBuilder — tree round-trip, validation, coercion, and
 * interaction tests.
 *
 * The component is the single editor for availability_rule (template),
 * visibility_rule (option), and requirements_override (giver offering).
 *
 * Adversarial review BLOCKERs (predicate-shape safety) and HIGHs
 * (missing leaf-swap-resets-params test) are pinned here.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { vi } from 'vitest';

import {
  coercePredicate,
  isEmpty,
  isGroup,
  isLeaf,
  PredicateBuilder,
  validatePredicate,
  type PredicateNode,
} from '../components/PredicateBuilder';

const LEAVES = [
  { name: 'has_distinction', params: [{ name: 'slug', type: 'str' as const }] },
  { name: 'min_character_level', params: [{ name: 'level', type: 'int' as const }] },
  { name: 'has_thread', params: [] as Array<{ name: string; type: 'str' }> },
];

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    usePredicateLeaves: () => ({
      data: LEAVES,
      isLoading: false,
      isSuccess: true,
      isError: false,
    }),
  };
});

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function Harness({ initial }: { initial: PredicateNode }) {
  const [value, setValue] = useState<PredicateNode>(initial);
  return (
    <>
      <PredicateBuilder value={value} onChange={setValue} label="Test" />
      <pre data-testid="state">{JSON.stringify(value)}</pre>
    </>
  );
}

describe('PredicateBuilder', () => {
  describe('type guards', () => {
    it('isEmpty distinguishes {} from non-empty', () => {
      expect(isEmpty({})).toBe(true);
      expect(isEmpty({ op: 'AND', of: [] })).toBe(false);
    });

    it('isGroup and isLeaf are mutually exclusive', () => {
      const group: PredicateNode = { op: 'OR', of: [] };
      const leaf: PredicateNode = { leaf: 'has_thread', params: {} };
      expect(isGroup(group)).toBe(true);
      expect(isLeaf(group)).toBe(false);
      expect(isGroup(leaf)).toBe(false);
      expect(isLeaf(leaf)).toBe(true);
    });
  });

  it('renders the empty-slot buttons when value is {}', () => {
    render(<Harness initial={{}} />, { wrapper: wrapper() });
    expect(screen.getByRole('button', { name: '+ Group' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Leaf' })).toBeInTheDocument();
  });

  it('promotes {} to a group when + Group is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{}} />, { wrapper: wrapper() });
    await user.click(screen.getByRole('button', { name: '+ Group' }));
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}');
    expect(state).toEqual({ op: 'AND', of: [] });
  });

  it('promotes {} to a (pending) leaf when + Leaf is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{}} />, { wrapper: wrapper() });
    await user.click(screen.getByRole('button', { name: '+ Leaf' }));
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}');
    expect(state).toEqual({ leaf: '', params: {} });
    // BLOCKER fix: the row visibly marks itself as not-yet-safe.
    const row = screen.getByTestId('predicate-leaf');
    expect(row.getAttribute('data-empty')).toBe('true');
  });

  it('renders a nested group with a leaf child', () => {
    render(
      <Harness
        initial={{
          op: 'AND',
          of: [{ leaf: 'has_thread', params: {} }],
        }}
      />,
      { wrapper: wrapper() }
    );
    expect(screen.getByTestId('predicate-group')).toBeInTheDocument();
    expect(screen.getByTestId('predicate-leaf')).toBeInTheDocument();
  });

  it('round-trips serialization of a deeply nested rule', () => {
    const nested: PredicateNode = {
      op: 'AND',
      of: [
        { leaf: 'has_distinction', params: { slug: 'brave' } },
        {
          op: 'OR',
          of: [
            { leaf: 'min_character_level', params: { level: '5' } },
            { leaf: 'has_thread', params: {} },
          ],
        },
      ],
    };
    render(<Harness initial={nested} />, { wrapper: wrapper() });
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}');
    expect(state).toEqual(nested);
  });
});

describe('validatePredicate (BLOCKER fix)', () => {
  it('accepts an empty tree', () => {
    expect(validatePredicate({}, LEAVES)).toEqual([]);
  });

  it('rejects an empty leaf — the shape that crashes _eligible_templates', () => {
    const tree: PredicateNode = { leaf: '', params: {} };
    const errors = validatePredicate(tree, LEAVES);
    expect(errors.length).toBeGreaterThan(0);
    expect(errors.some((e) => /empty leaf/i.test(e))).toBe(true);
  });

  it('rejects an unknown leaf name', () => {
    const tree: PredicateNode = { leaf: 'made_up_resolver', params: {} };
    expect(validatePredicate(tree, LEAVES)).toContainEqual(expect.stringContaining('unknown leaf'));
  });

  it('rejects a leaf missing a required param', () => {
    const tree: PredicateNode = { leaf: 'has_distinction', params: {} };
    expect(validatePredicate(tree, LEAVES)).toContainEqual(
      expect.stringContaining('"slug" is required')
    );
  });

  it('rejects a NOT group with two operands', () => {
    const tree: PredicateNode = {
      op: 'NOT',
      // The tree shape allows it at construction time; validator must catch.
      of: [{ leaf: 'has_thread', params: {} }] as [PredicateNode],
    };
    // Simulate a NOT with two operands (bypassing the TS [N] tuple).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (tree as any).of = [
      { leaf: 'has_thread', params: {} },
      { leaf: 'has_thread', params: {} },
    ];
    expect(validatePredicate(tree, LEAVES)).toContainEqual(
      expect.stringContaining('NOT must have exactly one operand')
    );
  });

  it('walks into nested groups', () => {
    const tree: PredicateNode = {
      op: 'AND',
      of: [
        { leaf: '', params: {} },
        { op: 'OR', of: [] },
      ],
    };
    const errors = validatePredicate(tree, LEAVES);
    expect(errors.length).toBeGreaterThan(0);
  });
});

describe('coercePredicate (BLOCKER fix — int params must not stay strings)', () => {
  it('passes empty tree through', () => {
    expect(coercePredicate({}, LEAVES)).toEqual({});
  });

  it('coerces int-typed params from string to number', () => {
    const tree: PredicateNode = {
      leaf: 'min_character_level',
      params: { level: '5' },
    };
    const coerced = coercePredicate(tree, LEAVES) as { leaf: string; params: { level: number } };
    expect(coerced.params.level).toBe(5);
    expect(typeof coerced.params.level).toBe('number');
  });

  it('preserves str-typed params as strings', () => {
    const tree: PredicateNode = { leaf: 'has_distinction', params: { slug: 'brave' } };
    expect(coercePredicate(tree, LEAVES)).toEqual({
      leaf: 'has_distinction',
      params: { slug: 'brave' },
    });
  });

  it('coerces inside nested groups', () => {
    const tree: PredicateNode = {
      op: 'AND',
      of: [{ leaf: 'min_character_level', params: { level: '12' } }],
    };
    const coerced = coercePredicate(tree, LEAVES) as { op: string; of: PredicateNode[] };
    const inner = coerced.of[0] as { leaf: string; params: { level: number } };
    expect(inner.params.level).toBe(12);
  });
});

describe('PredicateBuilder interactions', () => {
  it('resets params when leaf type swaps — the subtle invariant the docstring promised', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ leaf: 'has_distinction', params: { slug: 'brave' } }} />, {
      wrapper: wrapper(),
    });
    // Open the leaf-type select.
    const select = screen.getByRole('combobox');
    await user.click(select);
    // Pick a different leaf.
    await user.click(screen.getByRole('option', { name: 'has_thread' }));
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}');
    expect(state).toEqual({ leaf: 'has_thread', params: {} });
    // The old `slug: 'brave'` param must be gone.
    expect(state.params.slug).toBeUndefined();
  });
});
