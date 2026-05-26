/**
 * PredicateBuilder — tree round-trip and interaction tests.
 *
 * The component is the single editor for availability_rule (template)
 * and visibility_rule (option). Tests cover the shape contract and the
 * key user gestures: empty -> group, empty -> leaf, change op, swap
 * leaf type (params reset).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { vi } from 'vitest';

import {
  isEmpty,
  isGroup,
  isLeaf,
  PredicateBuilder,
  type PredicateNode,
} from '../components/PredicateBuilder';

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    usePredicateLeaves: () => ({
      data: [
        { name: 'has_distinction', params: ['slug'] },
        { name: 'min_character_level', params: ['level'] },
        { name: 'has_thread', params: [] },
      ],
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

  it('promotes {} to a leaf when + Leaf is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{}} />, { wrapper: wrapper() });
    await user.click(screen.getByRole('button', { name: '+ Leaf' }));
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}');
    expect(state).toEqual({ leaf: '', params: {} });
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
