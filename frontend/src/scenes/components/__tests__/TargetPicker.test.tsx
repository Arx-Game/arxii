import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TargetPicker, type TargetCandidate } from '../TargetPicker';
import type { TargetSpec } from '../../actionTypes';

function makeSpec(overrides: Partial<TargetSpec> = {}): TargetSpec {
  return {
    kind: 'persona',
    cardinality: 'single',
    filters: {
      in_same_scene: true,
      in_same_zone: false,
      exclude_self: false,
      must_be_conscious: false,
    },
    ...overrides,
  };
}

const CANDIDATES: TargetCandidate[] = [
  { id: 1, name: 'Alice' },
  { id: 2, name: 'Bob' },
  { id: 3, name: 'Carol' },
];

describe('TargetPicker', () => {
  it('renders the candidates from the spec', () => {
    render(
      <TargetPicker
        spec={makeSpec()}
        candidates={CANDIDATES}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Carol')).toBeInTheDocument();
  });

  it('excludes self when filter is set and candidate has is_self=true', () => {
    const candidatesWithSelf: TargetCandidate[] = [
      { id: 1, name: 'Me', is_self: true },
      { id: 2, name: 'Bob' },
    ];
    render(
      <TargetPicker
        spec={makeSpec({
          filters: {
            in_same_scene: true,
            in_same_zone: false,
            exclude_self: true,
            must_be_conscious: false,
          },
        })}
        candidates={candidatesWithSelf}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByText('Me')).not.toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('single-select calls onConfirm with one id on click', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TargetPicker
        spec={makeSpec({ cardinality: 'single' })}
        candidates={CANDIDATES}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    await user.click(screen.getByText('Bob'));
    expect(onConfirm).toHaveBeenCalledWith([2]);
  });

  it('multi-select accumulates and confirms with full id list', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TargetPicker
        spec={makeSpec({ cardinality: 'area' })}
        candidates={CANDIDATES}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    await user.click(screen.getByText('Alice'));
    await user.click(screen.getByText('Carol'));
    // Confirm not called yet
    expect(onConfirm).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0]).toEqual(expect.arrayContaining([1, 3]));
    expect(onConfirm.mock.calls[0][0]).toHaveLength(2);
  });

  it('cancel button calls onCancel', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <TargetPicker
        spec={makeSpec()}
        candidates={CANDIDATES}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});
