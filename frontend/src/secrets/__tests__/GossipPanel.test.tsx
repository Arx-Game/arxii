/**
 * GossipPanel (#1572) — lists the active character's spreadable Level-1 secrets with their regional
 * heat, and offers seek / spread / quiet. Mocks the query + mutation hooks so the panel renders
 * synchronously.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { GossipPanel } from '../components/GossipPanel';
import type { GossipSecret } from '../types';

const mutate = vi.fn();

vi.mock('@/secrets/queries', () => ({
  useGossipQuery: vi.fn(),
  useGossipActionMutation: vi.fn(() => ({
    mutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
  })),
}));

import { useGossipQuery } from '@/secrets/queries';

const mockQuery = vi.mocked(useGossipQuery);

function mockRows(rows: GossipSecret[]): void {
  mockQuery.mockReturnValue({
    data: rows,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useGossipQuery>);
}

describe('GossipPanel', () => {
  it('prompts to pick a character when none is active', () => {
    mockRows([]);
    render(<GossipPanel viewerId={null} />);
    expect(screen.getByText(/select a character/i)).toBeInTheDocument();
  });

  it('lists spreadable gossip with its heat', () => {
    mockRows([{ id: 7, content: 'A juicy rumor.', heat: 3 }]);
    render(<GossipPanel viewerId={42} />);
    expect(screen.getByText('A juicy rumor.')).toBeInTheDocument();
    expect(screen.getByText(/heat here: 3/i)).toBeInTheDocument();
  });

  it('dispatches a plant when Spread is clicked', () => {
    mockRows([{ id: 7, content: 'A juicy rumor.', heat: 3 }]);
    render(<GossipPanel viewerId={42} />);
    fireEvent.click(screen.getByRole('button', { name: 'Spread' }));
    expect(mutate).toHaveBeenCalledWith({ action: 'plant', viewer: 42, secret: 7 });
  });

  it('dispatches a seek when Listen is clicked', () => {
    mockRows([]);
    render(<GossipPanel viewerId={42} />);
    fireEvent.click(screen.getByRole('button', { name: /listen for gossip/i }));
    expect(mutate).toHaveBeenCalledWith({ action: 'seek', viewer: 42 });
  });
});
