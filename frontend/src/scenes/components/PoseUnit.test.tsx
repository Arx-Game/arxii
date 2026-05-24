/**
 * Tests for PoseUnit combined pose+action renderer.
 * Phase 9, Task 9.2.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { PoseUnit } from './PoseUnit';
import type { Interaction } from '../types';

// Stub PoseUnitDetailPanel so this test doesn't need the combat query mocks.
vi.mock('./PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: ({ actionInteractionIds }: { actionInteractionIds: number[] }) => (
    <div data-testid="mock-detail-panel">{actionInteractionIds.join(',')}</div>
  ),
}));

function makeInteraction(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 1,
    persona: { id: 10, name: 'Alice' },
    content: 'Hello world',
    mode: 'pose',
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

describe('PoseUnit', () => {
  it('renders a POSE with two linked actions — header + 2 chips + body + reactions', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A well-crafted pose.',
      action_links: [
        {
          id: 100,
          ordering: 0,
          action_interaction: {
            id: 201,
            content: '[Strike] using Tidal Fury -- Success',
            mode: 'action',
            timestamp: '2026-01-01T00:00:01Z',
          },
        },
        {
          id: 101,
          ordering: 1,
          action_interaction: {
            id: 202,
            content: '[Shield] using Ward -- Partial',
            mode: 'action',
            timestamp: '2026-01-01T00:00:02Z',
          },
        },
      ],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    // Header persona name
    expect(screen.getByText('Alice')).toBeInTheDocument();

    // Two action chips
    const chips = screen.getByTestId('action-chips').querySelectorAll('button');
    expect(chips.length).toBe(2);
    expect(screen.getByText('[Strike] using Tidal Fury -- Success')).toBeInTheDocument();
    expect(screen.getByText('[Shield] using Ward -- Partial')).toBeInTheDocument();

    // Prose body
    expect(screen.getByText('A well-crafted pose.')).toBeInTheDocument();

    // Reactions footer (thumbs-up button always rendered)
    expect(screen.getByText('\u{1F44D}')).toBeInTheDocument();
  });

  it('renders a POSE without action links — narrative-only card, no chips', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A purely narrative pose.',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByText('A purely narrative pose.')).toBeInTheDocument();
    expect(screen.queryByTestId('action-chips')).toBeNull();
    expect(screen.getByTestId('pose-unit')).toBeInTheDocument();
  });

  it('renders a standalone ACTION as chip-only card', () => {
    const interaction = makeInteraction({
      mode: 'action',
      content: '[Strike] using Tidal Fury -- Success',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('pose-unit-action-standalone')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('toggles the detail panel on chip click', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A pose with an action.',
      action_links: [
        {
          id: 100,
          ordering: 0,
          action_interaction: {
            id: 201,
            content: '[Strike] using Tidal Fury -- Success',
            mode: 'action',
            timestamp: '2026-01-01T00:00:01Z',
          },
        },
      ],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    // Panel not visible initially
    expect(screen.queryByTestId('mock-detail-panel')).toBeNull();

    // Click chip to expand
    const chip = screen.getByTitle('Click to expand action details');
    fireEvent.click(chip);

    // Panel now visible with the action interaction ID
    expect(screen.getByTestId('mock-detail-panel')).toBeInTheDocument();
    expect(screen.getByTestId('mock-detail-panel')).toHaveTextContent('201');

    // Click again to collapse
    fireEvent.click(chip);
    expect(screen.queryByTestId('mock-detail-panel')).toBeNull();
  });

  it('calls onAddTarget on double-click of persona name', () => {
    const onAddTarget = vi.fn();
    const interaction = makeInteraction({ mode: 'pose' });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" onAddTarget={onAddTarget} />
      </Wrapper>
    );

    const span = screen.getByTitle('Double-click to add as target');
    fireEvent.doubleClick(span);
    expect(onAddTarget).toHaveBeenCalledWith('Alice');
  });
});
