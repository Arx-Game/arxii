import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ThreadCard } from '../ThreadCard';
import type { Thread, ThreadHubSummary } from '../../../types';

const makeThread = (overrides: Partial<Thread> = {}): Thread => ({
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'TRAIT',
  name: 'Test Thread',
  description: '',
  level: 30,
  developed_points: 50,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  ...overrides,
});

const makeSummary = (overrides: Partial<ThreadHubSummary> = {}): ThreadHubSummary => ({
  balances: [],
  ready_thread_ids: [],
  near_xp_lock_thread_ids: [],
  blocked_thread_ids: [],
  weaving_eligibility: {},
  ...overrides,
});

describe('ThreadCard', () => {
  it('renders thread name', () => {
    render(<ThreadCard thread={makeThread()} summary={makeSummary()} onClick={vi.fn()} />);
    expect(screen.getByText('Test Thread')).toBeInTheDocument();
  });

  it('renders "(unnamed)" when name is empty', () => {
    render(
      <ThreadCard thread={makeThread({ name: '' })} summary={makeSummary()} onClick={vi.fn()} />
    );
    expect(screen.getByText('(unnamed)')).toBeInTheDocument();
  });

  it('renders target_kind badge', () => {
    render(
      <ThreadCard
        thread={makeThread({ target_kind: 'TECHNIQUE' })}
        summary={makeSummary()}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByText('TECHNIQUE')).toBeInTheDocument();
  });

  it('renders level divided by 10', () => {
    render(
      <ThreadCard thread={makeThread({ level: 30 })} summary={makeSummary()} onClick={vi.fn()} />
    );
    expect(screen.getByText('Level 3')).toBeInTheDocument();
  });

  it('renders resonance name', () => {
    render(
      <ThreadCard
        thread={makeThread({ resonance_name: 'Praedari' })}
        summary={makeSummary()}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByText('Praedari')).toBeInTheDocument();
  });

  it('shows "normal" state when thread is not in any summary list', () => {
    render(
      <ThreadCard thread={makeThread({ id: 99 })} summary={makeSummary()} onClick={vi.fn()} />
    );
    expect(screen.getByTestId('thread-state-badge-normal')).toBeInTheDocument();
  });

  it('shows "ready" state when thread is in ready_thread_ids', () => {
    render(
      <ThreadCard
        thread={makeThread({ id: 5 })}
        summary={makeSummary({ ready_thread_ids: [5] })}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByTestId('thread-state-badge-ready')).toBeInTheDocument();
  });

  it('shows "near_xp_lock" state when thread is in near_xp_lock_thread_ids', () => {
    render(
      <ThreadCard
        thread={makeThread({ id: 5 })}
        summary={makeSummary({
          near_xp_lock_thread_ids: [
            { thread_id: 5, boundary_level: 30, xp_cost: 10, dev_points_to_boundary: 5 },
          ],
        })}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByTestId('thread-state-badge-near_xp_lock')).toBeInTheDocument();
  });

  it('shows "blocked" state when thread is in blocked_thread_ids', () => {
    render(
      <ThreadCard
        thread={makeThread({ id: 5 })}
        summary={makeSummary({ blocked_thread_ids: [5] })}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByTestId('thread-state-badge-blocked')).toBeInTheDocument();
  });

  it('blocked takes priority over near_xp_lock and ready', () => {
    render(
      <ThreadCard
        thread={makeThread({ id: 5 })}
        summary={makeSummary({
          blocked_thread_ids: [5],
          ready_thread_ids: [5],
          near_xp_lock_thread_ids: [
            { thread_id: 5, boundary_level: 30, xp_cost: 10, dev_points_to_boundary: 5 },
          ],
        })}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByTestId('thread-state-badge-blocked')).toBeInTheDocument();
  });

  it('calls onClick with the thread when clicked', () => {
    const handleClick = vi.fn();
    const thread = makeThread({ id: 7 });
    render(<ThreadCard thread={thread} summary={makeSummary()} onClick={handleClick} />);
    fireEvent.click(screen.getByTestId('thread-card-7'));
    expect(handleClick).toHaveBeenCalledOnce();
    expect(handleClick).toHaveBeenCalledWith(thread);
  });
});
