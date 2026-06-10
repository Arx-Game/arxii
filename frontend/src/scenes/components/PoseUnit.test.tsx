/**
 * Tests for PoseUnit combined pose+action renderer.
 * Phase 9, Task 9.2.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { PoseUnit } from './PoseUnit';
import type { Interaction } from '../types';

// Mock @/combat/queries — used by PoseUnitDetailPanel; prevents real fetches.
vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}));

import { useOutcomeDetails } from '@/combat/queries';
const mockUseOutcomeDetails = vi.mocked(useOutcomeDetails);

// Stub PoseUnitDetailPanel with the canonical data-testid.
// Renders actionInteractionIds as text content so tests can assert the
// correct IDs are forwarded; also calls the mocked useOutcomeDetails so
// "called with [id]" assertions work.
vi.mock('./PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: ({ actionInteractionIds }: { actionInteractionIds: number[] }) => (
    <div data-testid="pose-unit-detail-panel">{actionInteractionIds.join(',')}</div>
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
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOutcomeDetails.mockReturnValue({ data: [], isLoading: false } as ReturnType<
      typeof useOutcomeDetails
    >);
  });

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
    expect(screen.queryByTestId('pose-unit-detail-panel')).toBeNull();

    // Click chip to expand
    const chip = screen.getByTitle('Click to expand action details');
    fireEvent.click(chip);

    // Panel now visible with the action interaction ID
    expect(screen.getByTestId('pose-unit-detail-panel')).toBeInTheDocument();
    expect(screen.getByTestId('pose-unit-detail-panel')).toHaveTextContent('201');

    // Click again to collapse
    fireEvent.click(chip);
    expect(screen.queryByTestId('pose-unit-detail-panel')).toBeNull();
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

  // ---------------------------------------------------------------------------
  // Standalone ACTION expand affordance (#859)
  // ---------------------------------------------------------------------------

  it('standalone ACTION renders the expand control', () => {
    const interaction = makeInteraction({
      id: 42,
      mode: 'action',
      content: '[Frost Bolt] -- Success',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('standalone-action-expand')).toBeInTheDocument();
  });

  it('standalone ACTION expand reveals the detail panel with the interaction id', () => {
    const interaction = makeInteraction({
      id: 42,
      mode: 'action',
      content: '[Frost Bolt] -- Success',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    // Panel not visible before expand
    expect(screen.queryByTestId('pose-unit-detail-panel')).toBeNull();

    // Click the expand button
    fireEvent.click(screen.getByTestId('standalone-action-expand'));

    // Panel is now visible with the interaction's own id as content
    expect(screen.getByTestId('pose-unit-detail-panel')).toBeInTheDocument();
    expect(screen.getByTestId('pose-unit-detail-panel')).toHaveTextContent('42');
  });

  it('clicking expand again collapses the detail panel', () => {
    const interaction = makeInteraction({
      id: 42,
      mode: 'action',
      content: '[Frost Bolt] -- Success',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const btn = screen.getByTestId('standalone-action-expand');
    fireEvent.click(btn);
    expect(screen.getByTestId('pose-unit-detail-panel')).toBeInTheDocument();

    fireEvent.click(btn);
    expect(screen.queryByTestId('pose-unit-detail-panel')).toBeNull();
  });

  it('POSE-mode interactions do NOT render the standalone-action-expand control', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A narrative pose.',
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.queryByTestId('standalone-action-expand')).toBeNull();
  });
});

describe('PoseUnit outcome mode', () => {
  it('renders outcome narration as a combat-log line', () => {
    const interaction = makeInteraction({
      mode: 'outcome',
      persona: { id: 99, name: 'Narrator', thumbnail_url: '' },
      content: "Kira's Frost Bolt strikes the Pyromancer for 24 damage.",
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('pose-unit-outcome')).toBeInTheDocument();
    expect(screen.getByText(/Frost Bolt strikes the Pyromancer for 24/)).toBeInTheDocument();
  });

  it('renders no avatar, context menu, or target affordance for outcomes', () => {
    const interaction = makeInteraction({
      mode: 'outcome',
      persona: { id: 99, name: 'Narrator', thumbnail_url: '' },
      content: 'The dust settles.',
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.queryByTitle('Double-click to add as target')).toBeNull();
    expect(screen.queryByTestId('pose-unit')).toBeNull();
    expect(screen.queryByTestId('pose-unit-action-standalone')).toBeNull();
  });
});
