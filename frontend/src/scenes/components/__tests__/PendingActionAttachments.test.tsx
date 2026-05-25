import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PendingActionAttachments } from '../PendingActionAttachments';
import * as hooks from '../../hooks/usePendingUnlinkedActions';
import type { PendingUnlinkedActionRow } from '../../hooks/usePendingUnlinkedActions';

// ---------------------------------------------------------------------------
// Mock the hook — unit tests should not hit the network
// ---------------------------------------------------------------------------

vi.mock('../../hooks/usePendingUnlinkedActions');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAction(id: number, content: string): PendingUnlinkedActionRow {
  return { id, content, mode: 'action', timestamp: '2026-05-24T10:00:00Z' };
}

function makeHookResult(actions: PendingUnlinkedActionRow[]) {
  return { data: actions, isLoading: false };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const defaultProps = {
  sceneId: 'scene-1',
  personaId: 42,
  detachedIds: [] as number[],
  onDetach: vi.fn(),
  onUndoDetach: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PendingActionAttachments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when query returns empty list', () => {
    vi.mocked(hooks.usePendingUnlinkedActions).mockReturnValue(makeHookResult([]));

    const Wrapper = createWrapper();
    const { container } = render(
      <Wrapper>
        <PendingActionAttachments {...defaultProps} />
      </Wrapper>
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders one chip per action when query returns multiple items', () => {
    vi.mocked(hooks.usePendingUnlinkedActions).mockReturnValue(
      makeHookResult([makeAction(1, 'Tidal Fury vs Mire Knight'), makeAction(2, 'Shadow Step')])
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <PendingActionAttachments {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByText(/Tidal Fury vs Mire Knight/)).toBeInTheDocument();
    expect(screen.getByText(/Shadow Step/)).toBeInTheDocument();
  });

  it('clicking the dismiss button calls onDetach with the action id', async () => {
    const onDetach = vi.fn();
    vi.mocked(hooks.usePendingUnlinkedActions).mockReturnValue(
      makeHookResult([makeAction(7, 'Focused Strike')])
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <PendingActionAttachments {...defaultProps} onDetach={onDetach} />
      </Wrapper>
    );

    const detachBtn = screen.getByRole('button', { name: /detach action/i });
    await userEvent.click(detachBtn);

    expect(onDetach).toHaveBeenCalledWith(7);
  });

  it('detached chip shows strikethrough and undo affordance, not dismiss button', () => {
    vi.mocked(hooks.usePendingUnlinkedActions).mockReturnValue(
      makeHookResult([makeAction(3, 'Parry')])
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <PendingActionAttachments {...defaultProps} detachedIds={[3]} />
      </Wrapper>
    );

    // No detach button for a detached chip
    expect(screen.queryByRole('button', { name: /detach action/i })).not.toBeInTheDocument();
    // Undo affordance is present
    expect(screen.getByRole('button', { name: /undo detach/i })).toBeInTheDocument();
    // Content is struck through (has the line-through class)
    const struck = document.querySelector('.line-through');
    expect(struck).not.toBeNull();
  });

  it('clicking undo on a detached chip calls onUndoDetach with the action id', async () => {
    const onUndoDetach = vi.fn();
    vi.mocked(hooks.usePendingUnlinkedActions).mockReturnValue(
      makeHookResult([makeAction(5, 'Disarm')])
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <PendingActionAttachments {...defaultProps} detachedIds={[5]} onUndoDetach={onUndoDetach} />
      </Wrapper>
    );

    const undoBtn = screen.getByRole('button', { name: /undo detach/i });
    await userEvent.click(undoBtn);

    expect(onUndoDetach).toHaveBeenCalledWith(5);
  });
});
