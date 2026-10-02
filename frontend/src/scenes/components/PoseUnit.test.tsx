/**
 * Tests for PoseUnit combined pose+action renderer.
 * Phase 9, Task 9.2.
 */

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { PoseUnit } from './PoseUnit';
import type { Interaction } from '../types';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock @/combat/queries — used by PoseUnitDetailPanel; prevents real fetches.
// PoseUnit also renders PersonaContextMenu, which reads useDispatchPlayerAction
// + combatKeys for the duel-challenge affordance (#1181).
vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useDispatchPlayerAction: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  combatKeys: { duelChallengesAll: () => ['combat', 'duel-challenges'] },
}));

// Stub PoseUnitDetailPanel with the canonical data-testid. Renders
// actionInteractionIds as text content so tests can assert the correct IDs
// are forwarded; the real panel's fetching is covered by its own test file.
vi.mock('./PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: ({ actionInteractionIds }: { actionInteractionIds: number[] }) => (
    <div data-testid="pose-unit-detail-panel">{actionInteractionIds.join(',')}</div>
  ),
}));

// Mock the reaction-emoji catalog fetch (#1699) — the footer picker is
// catalog-driven now; the mutation helper stays mocked so no real POST fires.
vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    postInteractionReaction: vi.fn().mockResolvedValue(null),
    fetchReactionEmojiCatalog: vi
      .fn()
      .mockResolvedValue([{ emoji: '\u{1F44D}', valence: 0, sort_order: 0 }]),
  };
});

import { postInteractionReaction } from '../queries';
import { toast } from 'sonner';

// Stub EndorsementControl so PoseUnit mount tests can assert presence/absence
// without pulling in endorsement hook machinery. The stub renders data-* attributes
// carrying the forwarded mode and visibility so tests can verify prop forwarding.
vi.mock('./EndorsementControl', () => ({
  EndorsementControl: ({
    kind,
    interaction,
  }: {
    kind: string;
    interaction: { mode: string; visibility: string };
  }) => (
    <div
      data-testid={`endorsement-control-${kind}`}
      data-mode={interaction.mode}
      data-visibility={interaction.visibility}
    />
  ),
}));

describe('the actor in the line (#3858)', () => {
  it('renders the line as the body, with the leading name set heavier', () => {
    render(
      <Wrapper>
        <PoseUnit interaction={makeInteraction({ line: 'Alice waves.' })} sceneId="1" />
      </Wrapper>
    );
    const line = screen.getByTestId('actor-line');
    expect(line).toHaveTextContent('Alice waves.');
    expect(line).toHaveAttribute('data-actor', 'Alice');
    expect(screen.queryByText('Hello world')).not.toBeInTheDocument();
  });

  it('falls back to the recorded content on a row without a line', () => {
    render(
      <Wrapper>
        <PoseUnit interaction={makeInteraction()} sceneId="1" />
      </Wrapper>
    );
    expect(screen.getByText('Hello world')).toBeInTheDocument();
    expect(screen.queryByTestId('actor-line')).not.toBeInTheDocument();
  });

  it('reads a companion pose as the companion', () => {
    render(
      <Wrapper>
        <PoseUnit
          interaction={makeInteraction({
            line: 'Fang lifts his head.',
            attributed_companion: { id: 3, name: 'Fang' },
          })}
          sceneId="1"
        />
      </Wrapper>
    );
    expect(screen.getByTestId('actor-line')).toHaveAttribute('data-actor', 'Fang');
  });
});

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
    pose_kind: 'standard',
    endorsee_sheet_id: 20,
    endorsable_resonances: [{ id: 5, name: 'Courage' }],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
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
  });

  it('renders a POSE with two linked actions — header + 2 chips + body + reactions', async () => {
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

    // Reactions footer (picker buttons come from the reaction-emoji catalog, #1699)
    expect(await screen.findByText('\u{1F44D}')).toBeInTheDocument();
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

  it('auto-expands the detail panel on first paint when a link is critical (#996)', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A decisive blow.',
      action_links: [
        {
          id: 100,
          ordering: 0,
          has_critical_effect: true,
          action_interaction: {
            id: 201,
            content: '[Strike] using Tidal Fury -- Critical',
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

    // Panel is visible WITHOUT any click.
    expect(screen.getByTestId('pose-unit-detail-panel')).toBeInTheDocument();
    expect(screen.getByTestId('pose-unit-detail-panel')).toHaveTextContent('201');
  });

  it('stays collapsed on first paint when no link is critical', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      content: 'A glancing blow.',
      action_links: [
        {
          id: 100,
          ordering: 0,
          has_critical_effect: false,
          action_interaction: {
            id: 201,
            content: '[Strike] using Tidal Fury -- Partial',
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

  // ---------------------------------------------------------------------------
  // Chat-bubble restyle + avatar identity click (#2156)
  // ---------------------------------------------------------------------------

  it('clicking the avatar fires onAvatarClick with the interaction persona (POSE)', () => {
    const onAvatarClick = vi.fn();
    const interaction = makeInteraction({
      mode: 'pose',
      persona: { id: 10, name: 'Alice', thumbnail_url: '/alice.png' },
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" onAvatarClick={onAvatarClick} />
      </Wrapper>
    );

    fireEvent.click(screen.getByRole('button', { name: 'View Alice' }));
    expect(onAvatarClick).toHaveBeenCalledWith({
      id: 10,
      name: 'Alice',
      thumbnail_url: '/alice.png',
    });
  });

  it('clicking the avatar fires onAvatarClick on the standalone ACTION branch', () => {
    const onAvatarClick = vi.fn();
    const interaction = makeInteraction({
      mode: 'action',
      persona: { id: 10, name: 'Alice', thumbnail_url: undefined },
      action_links: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" onAvatarClick={onAvatarClick} />
      </Wrapper>
    );

    fireEvent.click(screen.getByRole('button', { name: 'View Alice' }));
    expect(onAvatarClick).toHaveBeenCalledWith({ id: 10, name: 'Alice', thumbnail_url: null });
  });

  it('avatar is not an interactive button when onAvatarClick is not provided', () => {
    const interaction = makeInteraction({ mode: 'pose' });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.queryByRole('button', { name: 'View Alice' })).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Right-click on the avatar opens the persona menu (#4030) — left-click keeps
  // opening the character card (covered above); a right-click reaches the same
  // action menu the name already offers.
  // ---------------------------------------------------------------------------

  it('right-clicking the avatar opens the persona menu with Look and View sheet', async () => {
    const onAvatarClick = vi.fn();
    const interaction = makeInteraction({
      mode: 'pose',
      persona: { id: 10, name: 'Alice', thumbnail_url: '/alice.png' },
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" onAvatarClick={onAvatarClick} />
      </Wrapper>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'View Alice' }));
    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Look', 'View sheet']);
    // The right-click never fires the left-click card-open handler.
    expect(onAvatarClick).not.toHaveBeenCalled();
  });

  it('POSE branch still exposes data-testid="pose-unit" as a chat bubble', () => {
    const interaction = makeInteraction({ mode: 'pose' });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const bubble = screen.getByTestId('pose-unit');
    expect(bubble).toHaveClass('rounded-lg');
    expect(bubble).toHaveClass('bg-muted/40');
    expect(bubble).not.toHaveClass('border-b');
  });

  it('standalone ACTION branch also renders as a bubble', () => {
    const interaction = makeInteraction({ mode: 'action', action_links: [] });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const bubble = screen.getByTestId('pose-unit-action-standalone');
    expect(bubble).toHaveClass('rounded-lg');
    expect(bubble).toHaveClass('bg-muted/40');
    expect(bubble).not.toHaveClass('border-b');
  });

  it('outcome branch keeps its muted-system-notice look with no border', () => {
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

    const notice = screen.getByTestId('pose-unit-outcome');
    expect(notice).toHaveClass('italic');
    expect(notice).toHaveClass('text-muted-foreground');
    expect(notice).not.toHaveClass('border-b');
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

// ---------------------------------------------------------------------------
// Endorsement control mounting (#1138)
// ---------------------------------------------------------------------------

describe('PoseUnit endorsement control mounting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ENTRY pose renders THREE endorsement controls (pose + entry + style)', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      pose_kind: 'entry',
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('endorsement-control-pose')).toBeInTheDocument();
    expect(screen.getByTestId('endorsement-control-entry')).toBeInTheDocument();
    expect(screen.getByTestId('endorsement-control-style')).toBeInTheDocument();
  });

  it('STANDARD pose renders pose + style controls, no entry', () => {
    const interaction = makeInteraction({
      mode: 'pose',
      pose_kind: 'standard',
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('endorsement-control-pose')).toBeInTheDocument();
    expect(screen.getByTestId('endorsement-control-style')).toBeInTheDocument();
    expect(screen.queryByTestId('endorsement-control-entry')).toBeNull();
  });

  it('OUTCOME branch renders NO endorsement controls', () => {
    const interaction = makeInteraction({
      mode: 'outcome',
      persona: { id: 99, name: 'Narrator', thumbnail_url: '' },
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.queryByTestId('endorsement-control-pose')).toBeNull();
    expect(screen.queryByTestId('endorsement-control-entry')).toBeNull();
    expect(screen.queryByTestId('endorsement-control-style')).toBeNull();
  });

  it('standalone ACTION branch also renders pose + style endorsement controls', () => {
    const interaction = makeInteraction({
      mode: 'action',
      pose_kind: 'standard',
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.getByTestId('endorsement-control-pose')).toBeInTheDocument();
    expect(screen.getByTestId('endorsement-control-style')).toBeInTheDocument();
  });

  // WHISPER and VERY_PRIVATE suppression is tested at the correct layer:
  // EndorsementControl.test.tsx covers "hides for WHISPER mode" and "hides for
  // VERY_PRIVATE visibility". PoseUnit's only responsibility is to mount
  // EndorsementControl and forward the interaction prop — the control self-hides.
  // The tests below verify that PoseUnit does pass the interaction's mode/visibility
  // through to EndorsementControl, so the real component receives the data it needs
  // to apply its own guard.

  it('whisper pose: PoseUnit forwards interaction with mode=whisper to EndorsementControl', () => {
    const interaction = makeInteraction({ mode: 'whisper', pose_kind: 'standard' });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    // The stub renders data-mode from the forwarded interaction prop.
    // If PoseUnit passes the right interaction, the real EndorsementControl will
    // see mode='whisper' and return null — suppression tested in EndorsementControl.test.tsx.
    const control = screen.getByTestId('endorsement-control-pose');
    expect(control).toHaveAttribute('data-mode', 'whisper');
  });

  it('very_private pose: PoseUnit forwards interaction with visibility=very_private to EndorsementControl', () => {
    const interaction = makeInteraction({ visibility: 'very_private', pose_kind: 'standard' });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const control = screen.getByTestId('endorsement-control-pose');
    expect(control).toHaveAttribute('data-visibility', 'very_private');
  });
});

// ---------------------------------------------------------------------------
// Regard-bump confirmation toast (#2158)
// ---------------------------------------------------------------------------

describe('PoseUnit reaction regard-bump toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('toasts the bump message on a successful regard bump (#2158)', async () => {
    vi.mocked(postInteractionReaction).mockResolvedValue({
      bump_applied: true,
      bump_message: 'Your regard for Elena warms.',
    });
    const interaction = makeInteraction({ mode: 'pose' });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const emojiButton = await screen.findByText('\u{1F44D}');
    fireEvent.click(emojiButton);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Your regard for Elena warms.');
    });
  });

  it('does not toast when the reaction resolves with no bump message (#2158)', async () => {
    vi.mocked(postInteractionReaction).mockResolvedValue({
      bump_applied: false,
      bump_message: null,
    });
    const interaction = makeInteraction({ mode: 'pose' });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const emojiButton = await screen.findByText('\u{1F44D}');
    fireEvent.click(emojiButton);

    await waitFor(() => {
      expect(postInteractionReaction).toHaveBeenCalled();
    });

    expect(toast.success).not.toHaveBeenCalled();
  });
});

// #3787 Task 7 -- the parent-reply chip (demo Screen 2), replacing the
// placeholder "Replying to pose {id}".
describe('parent-reply chip', () => {
  it('renders nothing when the pose has no reply_to', () => {
    const interaction = makeInteraction({ reply_to: null });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );
    expect(screen.queryByTestId('parent-reference')).toBeNull();
  });

  it('shows "Answering" plus the resolved parent\'s quoted excerpt, and reveals the parent content on click', () => {
    const parent = makeInteraction({
      id: 5,
      content: "Kira's Frost Bolt strikes Corvin for 24 damage, leaving them Staggered.",
      timestamp: '2026-01-01T00:00:05Z',
    });
    const interaction = makeInteraction({
      id: 6,
      reply_to: { id: '5', timestamp: '2026-01-01T00:00:05Z' },
    });
    const interactionsById = new Map([[parent.id, parent]]);

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" interactionsById={interactionsById} />
      </Wrapper>
    );

    const chip = screen.getByTestId('parent-chip-5');
    expect(chip).toHaveTextContent('Answering');
    expect(chip).toHaveTextContent(
      "Kira's Frost Bolt strikes Corvin for 24 damage, leaving them Staggered."
    );
    // The chip never re-derives an actor -- the parent's persona name must
    // not appear anywhere near it.
    expect(chip).not.toHaveTextContent(parent.persona.name);
    expect(screen.queryByTestId('parent-reveal-5')).toBeNull();

    fireEvent.click(chip);
    const revealed = screen.getByTestId('parent-reveal-5');
    expect(revealed).toHaveTextContent(
      "Kira's Frost Bolt strikes Corvin for 24 damage, leaving them Staggered."
    );
    expect(revealed).not.toHaveTextContent(parent.persona.name);
  });

  it('degrades to a plain chip with no quote when the parent is not in the loaded window', () => {
    const interaction = makeInteraction({
      id: 6,
      reply_to: { id: '999', timestamp: '2026-01-01T00:00:05Z' },
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const chip = screen.getByTestId('parent-chip-999');
    expect(chip).toHaveTextContent('Answering');
    // Nothing to reveal -- clicking does not throw and nothing appears.
    fireEvent.click(chip);
    expect(screen.queryByTestId('parent-reveal-999')).toBeNull();
  });
});

// Demo-fidelity fix round: F1 (Screen 3) -- a row carrying `narrates` renders
// in the narration form, not as a pose bubble with a speaker and Kudos.
describe('narration rows (#4101, demo Screen 3, F1)', () => {
  const narratesCrossing = {
    prompt_id: 1,
    kind: 'crossing' as const,
    kind_label: 'Crossing',
    subject_name: 'Rowan Ashcombe',
    subject_persona_id: 30,
  };

  it('renders a room narration line with no speaker name or Kudos, tagged for the narration block', () => {
    const interaction = makeInteraction({
      mode: 'emit',
      content: "The chapel floor groans and settles under Rowan's feet.",
      narrates: narratesCrossing,
      receiver_persona_ids: [],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    const block = screen.getByTestId('pose-unit-narration');
    expect(block).toHaveAttribute('role', 'note');
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    expect(screen.queryByText('Kudos')).not.toBeInTheDocument();
    expect(screen.queryByTestId('nominate-button')).not.toBeInTheDocument();
    expect(screen.getByText(/part of Rowan Ashcombe's Crossing/)).toBeInTheDocument();
  });

  it('renders a receiver-scoped narration as its own private block, not a pose bubble', () => {
    const interaction = makeInteraction({
      mode: 'whisper',
      content: "The stone remembers your mother's hand on this rail, Rowan.",
      narrates: narratesCrossing,
      receiver_persona_ids: [30],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );

    expect(screen.queryByTestId('pose-unit-narration')).not.toBeInTheDocument();
    const block = screen.getByTestId('pose-unit-narration-private');
    expect(block).toHaveAttribute('role', 'note');
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    expect(screen.queryByText('Kudos')).not.toBeInTheDocument();
    expect(screen.getByText(/visible only to Rowan Ashcombe/)).toBeInTheDocument();
  });
});
