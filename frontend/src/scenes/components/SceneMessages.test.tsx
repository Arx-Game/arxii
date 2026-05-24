import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { SceneMessages } from './SceneMessages';
import type { Interaction } from '../types';

// Stub PoseUnitDetailPanel to avoid combat query mocks in this test file.
vi.mock('./PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: () => <div data-testid="mock-detail-panel" />,
}));

function makeInteraction(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 1,
    persona: { id: 10, name: 'Alice' },
    content: 'Hello world',
    mode: 'say',
    visibility: 'default',
    timestamp: '2026-01-01T00:00:00Z',
    scene: 1,
    reactions: [],
    is_favorited: false,
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    action_links: [],
    ...overrides,
  };
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </Provider>
  );
}

describe('SceneMessages', () => {
  it('calls onAddTarget when persona name is double-clicked', () => {
    const onAddTarget = vi.fn();
    const interactions = [
      makeInteraction({ id: 1, persona: { id: 10, name: 'Alice' } }),
      makeInteraction({ id: 2, persona: { id: 20, name: 'Bob' } }),
    ];

    render(
      <Wrapper>
        <SceneMessages sceneId="1" filteredInteractions={interactions} onAddTarget={onAddTarget} />
      </Wrapper>
    );

    const spans = screen.getAllByTitle('Double-click to add as target');
    // First span is Alice
    fireEvent.doubleClick(spans[0]);

    expect(onAddTarget).toHaveBeenCalledWith('Alice');
  });

  it('renders filtered interactions when provided', () => {
    const interactions = [
      makeInteraction({ id: 1, content: 'First message', persona: { id: 10, name: 'Alice' } }),
      makeInteraction({ id: 2, content: 'Second message', persona: { id: 20, name: 'Bob' } }),
    ];

    render(
      <Wrapper>
        <SceneMessages sceneId="1" filteredInteractions={interactions} />
      </Wrapper>
    );

    expect(screen.getByText(/First message/)).toBeInTheDocument();
    expect(screen.getByText(/Second message/)).toBeInTheDocument();
  });

  it('collapses ACTION rows that are linked to a POSE via action_links', () => {
    // Pose references action ID 99 via action_links.
    const pose = makeInteraction({
      id: 1,
      mode: 'pose',
      content: 'A narrative pose.',
      persona: { id: 10, name: 'Alice' },
      action_links: [
        {
          id: 100,
          ordering: 0,
          action_interaction: {
            id: 99,
            content: '[Strike] using Tidal Fury -- Success',
            mode: 'action',
            timestamp: '2026-01-01T00:00:01Z',
          },
        },
      ],
    });

    // Standalone action with ID 99 — should be collapsed (rendered inside pose chip).
    const action = makeInteraction({
      id: 99,
      mode: 'action',
      content: '[Strike] using Tidal Fury -- Success',
      persona: { id: 10, name: 'Alice' },
      action_links: [],
    });

    // Unrelated action not linked to any pose — should render standalone.
    const standaloneAction = makeInteraction({
      id: 77,
      mode: 'action',
      content: '[Defend] using Shield -- Partial',
      persona: { id: 20, name: 'Bob' },
      action_links: [],
    });

    render(
      <Wrapper>
        <SceneMessages
          sceneId="1"
          filteredInteractions={[pose, action, standaloneAction]}
        />
      </Wrapper>
    );

    // The POSE unit should be rendered (contains its chip inline).
    expect(screen.getByTestId('pose-unit')).toBeInTheDocument();

    // The linked ACTION (id=99) should NOT render as its own standalone row.
    // We check there is exactly one standalone action (Bob's).
    const standaloneRows = screen.getAllByTestId('pose-unit-action-standalone');
    expect(standaloneRows.length).toBe(1);
  });
});
