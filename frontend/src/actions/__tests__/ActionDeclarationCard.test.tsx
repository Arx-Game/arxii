/**
 * Tests for ActionDeclarationCard — Phase 5.1 and 5.2.
 * Task 5.3 (effort, I/C chip, cost preview) tests added in the next commit.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { ActionDeclarationCard } from '../ActionDeclarationCard';
import type { ActionContext } from '../types';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

import { fetchAvailableActions } from '@/scenes/actionQueries';

const mockedFetchActions = fetchAvailableActions as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function emptyContext(overrides?: Partial<ActionContext>): ActionContext {
  return {
    slot: 'focused',
    effort: 'MEDIUM',
    strainCommitment: 0,
    ...overrides,
  };
}

const MOCK_TECHNIQUES = [
  {
    backend: 'MAGIC',
    display_name: 'Tidal Fury',
    description: 'A powerful wave attack',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Attack' },
    action_template: null,
    ref: {
      backend: 'MAGIC',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: 101,
      registry_key: null,
    },
  },
  {
    backend: 'MAGIC',
    display_name: 'Storm Surge',
    description: 'A defensive surge',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Defense' },
    action_template: null,
    ref: {
      backend: 'MAGIC',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: 102,
      registry_key: null,
    },
  },
];

// ---------------------------------------------------------------------------
// Task 5.1 — skeleton + empty-state tests
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.1 skeleton', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  });

  it('renders with empty context (no technique picked yet)', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    // Wait for the loading state to clear after React Query resolves.
    await waitFor(() => {
      expect(screen.getByText(/pick a technique/i)).toBeInTheDocument();
    });
  });

  it('renders all section headings', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/^technique$/i)).toBeInTheDocument();
    expect(screen.getByText(/^target$/i)).toBeInTheDocument();
    expect(screen.getByText(/^effort$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cost$/i)).toBeInTheDocument();
    expect(screen.getByText(/thread pulls/i)).toBeInTheDocument();
  });

  it('renders the slot name in the header', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext({ slot: 'passive-physical' })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/passive physical/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 5.2 — technique + target pickers
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.2 technique picker', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
  });

  it('lists available techniques for selection', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByText('Tidal Fury')).toBeInTheDocument();
      expect(screen.getByText('Storm Surge')).toBeInTheDocument();
    });
  });

  it('emits onContextChange when a technique is selected', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={onContextChange}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByText('Tidal Fury'));
    await userEvent.click(screen.getByText('Tidal Fury'));

    expect(onContextChange).toHaveBeenCalledWith(
      expect.objectContaining({ techniqueId: 101 })
    );
  });

  it('highlights the selected technique', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByText('Tidal Fury'));

    const tidalFuryBtn = screen.getByText('Tidal Fury').closest('button');
    expect(tidalFuryBtn).toHaveClass('border-primary');
  });
});
