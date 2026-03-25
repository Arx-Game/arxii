import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { SceneMessages } from './SceneMessages';
import type { Interaction } from '../types';

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
});
