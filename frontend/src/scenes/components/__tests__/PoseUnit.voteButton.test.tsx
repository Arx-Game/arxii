/**
 * Targeted test: VoteButton visibility gating in PoseUnit (#2161).
 *
 * PoseUnit mounts VoteButton beside ReactionsFooter (both the POSE and
 * standalone-ACTION branches), but only when the pose does not belong to the
 * viewer — VoteButton itself carries no self-guard (the backend rejects
 * self-votes; this gate is UX only), so PoseUnit computes the same
 * viewer-persona signal EndorsementControl uses and decides whether to mount.
 *
 * Scope: gating only. VoteButton's own budget-disabled behavior is its own
 * concern and isn't retested here.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Interaction } from '../../types';

// Mock @/combat/queries — used by PersonaContextMenu's duel-challenge affordance (#1181).
vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useDispatchPlayerAction: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  combatKeys: { duelChallengesAll: () => ['combat', 'duel-challenges'] },
}));

// Stub PoseUnitDetailPanel — irrelevant to VoteButton gating.
vi.mock('../PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: () => <div data-testid="pose-unit-detail-panel" />,
}));

// Stub EndorsementControl — irrelevant to VoteButton gating; covered by its own tests.
vi.mock('../EndorsementControl', () => ({
  EndorsementControl: () => null,
}));

// Mock the reaction-emoji catalog fetch (#1699) so ReactionsFooter's useQuery
// doesn't hit the real network.
vi.mock('../../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../queries')>();
  return {
    ...actual,
    postInteractionReaction: vi.fn().mockResolvedValue(null),
    fetchReactionEmojiCatalog: vi.fn().mockResolvedValue([]),
  };
});

// Viewer persona resolution — mirrors EndorsementControl.test.tsx's idiom.
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'ViewerChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 7,
        active_persona_id: 7,
      },
    ],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'ViewerChar' }, auth: {} })
  ),
}));

// Vote hooks — mocked so VoteButton renders without hitting the network.
const mockCastVote = vi.fn();
const mockRemoveVote = vi.fn();
vi.mock('@/progression/voteQueries', () => ({
  useMyVotesQuery: vi.fn(() => ({ data: [] })),
  useVoteBudgetQuery: vi.fn(() => ({
    data: { base_votes: 5, scene_bonus_votes: 0, votes_spent: 0, votes_remaining: 5 },
  })),
  useCastVoteMutation: vi.fn(() => ({ mutate: mockCastVote, isPending: false })),
  useRemoveVoteMutation: vi.fn(() => ({ mutate: mockRemoveVote, isPending: false })),
}));

import { PoseUnit } from '../PoseUnit';

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
    endorsable_resonances: [],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

function Wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('PoseUnit — VoteButton gating (#2161)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders VoteButton on another persona's pose in a scene", () => {
    // Alice (id 10) is not the viewer (primary_persona_id 7).
    const interaction = makeInteraction({ mode: 'pose', persona: { id: 10, name: 'Alice' } });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );
    expect(screen.getByTitle(/vote/i)).toBeInTheDocument();
  });

  it("hides VoteButton on the viewer's own pose", () => {
    // persona.id === 7 matches the mocked viewer's primary_persona_id.
    const interaction = makeInteraction({
      mode: 'pose',
      persona: { id: 7, name: 'ViewerChar' },
    });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );
    expect(screen.queryByTitle(/vote/i)).toBeNull();
  });

  it("renders VoteButton on another persona's standalone ACTION in a scene", () => {
    const interaction = makeInteraction({
      mode: 'action',
      persona: { id: 10, name: 'Alice' },
      action_links: [],
    });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );
    expect(screen.getByTitle(/vote/i)).toBeInTheDocument();
  });

  it("hides VoteButton on the viewer's own standalone ACTION", () => {
    const interaction = makeInteraction({
      mode: 'action',
      persona: { id: 7, name: 'ViewerChar' },
      action_links: [],
    });
    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="1" />
      </Wrapper>
    );
    expect(screen.queryByTitle(/vote/i)).toBeNull();
  });
});
