import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ThreadList } from '../components/ThreadList';
import type { Thread } from '../types';
import { useThreads } from '../queries';

vi.mock('../queries', () => ({
  useThreads: vi.fn(),
}));

const mockThread: Thread = {
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Resonance One',
  target_kind: 'TRAIT',
  name: 'Test Thread',
  description: 'A test thread',
  level: 20,
  developed_points: 50,
  path_cap: 10,
  anchor_cap: 20,
  effective_cap: 10,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
};

const mockThread2: Thread = {
  id: 2,
  owner: 100,
  resonance: 2,
  resonance_name: 'Resonance Two',
  target_kind: 'TECHNIQUE',
  name: 'Another Thread',
  description: 'Another test thread',
  level: 30,
  developed_points: 75,
  path_cap: 10,
  anchor_cap: 30,
  effective_cap: 10,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
};

const mockThread3: Thread = {
  id: 3,
  owner: 100,
  resonance: 1,
  resonance_name: 'Resonance One',
  target_kind: 'FACET',
  name: 'Capstone Thread',
  description: 'A capstone thread',
  level: 40,
  developed_points: 100,
  path_cap: 10,
  anchor_cap: null,
  effective_cap: null,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
};

describe('ThreadList', () => {
  it('renders empty state when no threads', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList />);
    expect(screen.getByText('No threads.')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders threads with name, target_kind, level, and resonance', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [mockThread],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList />);
    expect(screen.getByText('Test Thread')).toBeInTheDocument();
    expect(screen.getByText('TRAIT')).toBeInTheDocument();
    expect(screen.getByText('Level 2')).toBeInTheDocument();
    expect(screen.getByText('Resonance One')).toBeInTheDocument();
  });

  it('renders multiple threads', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [mockThread, mockThread2],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList />);
    expect(screen.getByText('Test Thread')).toBeInTheDocument();
    expect(screen.getByText('Another Thread')).toBeInTheDocument();
    expect(screen.getAllByText(/TRAIT|TECHNIQUE/)).toHaveLength(2);
  });

  it('filters threads by targetKind when prop is provided', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: {
        count: 3,
        next: null,
        previous: null,
        results: [mockThread, mockThread2, mockThread3],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList targetKind="TRAIT" />);
    expect(screen.getByText('Test Thread')).toBeInTheDocument();
    expect(screen.queryByText('Another Thread')).not.toBeInTheDocument();
    expect(screen.queryByText('Capstone Thread')).not.toBeInTheDocument();
  });

  it('filters threads by multiple kinds (comma-separated if applicable)', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: {
        count: 3,
        next: null,
        previous: null,
        results: [mockThread, mockThread2, mockThread3],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    // Test with single kind
    const { rerender } = render(<ThreadList targetKind="TECHNIQUE" />);
    expect(screen.queryByText('Test Thread')).not.toBeInTheDocument();
    expect(screen.getByText('Another Thread')).toBeInTheDocument();
    expect(screen.queryByText('Capstone Thread')).not.toBeInTheDocument();

    // Rerender with different kind
    rerender(<ThreadList targetKind="FACET" />);
    expect(screen.queryByText('Test Thread')).not.toBeInTheDocument();
    expect(screen.queryByText('Another Thread')).not.toBeInTheDocument();
    expect(screen.getByText('Capstone Thread')).toBeInTheDocument();
  });

  it('shows all threads when targetKind is not provided', () => {
    vi.mocked(useThreads).mockReturnValue({
      data: {
        count: 3,
        next: null,
        previous: null,
        results: [mockThread, mockThread2, mockThread3],
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useThreads>);

    render(<ThreadList />);
    expect(screen.getByText('Test Thread')).toBeInTheDocument();
    expect(screen.getByText('Another Thread')).toBeInTheDocument();
    expect(screen.getByText('Capstone Thread')).toBeInTheDocument();
  });
});
