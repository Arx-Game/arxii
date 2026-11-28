/**
 * Tests for EndorsementControl (#1138, #5327) — resonance-picker + endorsement badge strip
 * for pose, scene-entry and style endorsements. A pose's menu lists every resonance under its
 * affinity, a pick waits for the poser, and the poser accepts or declines.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Interaction } from '../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockCreatePoseEndorsement = vi.fn();
const mockDeletePoseEndorsement = vi.fn();
const mockChangePoseEndorsement = vi.fn();
const mockAnswerPoseEndorsement = vi.fn();
const mockCreateSceneEntryEndorsement = vi.fn();
const mockCreateStyleEndorsement = vi.fn();

// Mutable mutation-state stand-in for useCreateStyleEndorsement — style
// endorsements carry no persisted "endorsed by me" flag on the Interaction
// payload (verified: the backend serializer only exposes entry_endorsed_by_me),
// so the component derives its endorsed-indicator + error display from the
// mutation object's isSuccess/isError/error, same as react-query would return.
let styleMutationState: {
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  error: Error | null;
} = {
  isPending: false,
  isSuccess: false,
  isError: false,
  error: null,
};

// The resonance catalog the pose menu lists (#5327): every resonance, under its affinity.
const CATALOG = [
  { id: 41, name: 'Fury', affinity: 1, affinity_name: 'Primal' },
  { id: 42, name: 'Grief', affinity: 1, affinity_name: 'Primal' },
  { id: 43, name: 'Mercy', affinity: 2, affinity_name: 'Celestial' },
  { id: 44, name: 'Cruelty', affinity: 3, affinity_name: 'Abyssal' },
];
vi.mock('@/magic/queries', () => ({
  useResonanceCatalog: () => ({ data: CATALOG }),
}));

vi.mock('../../queries', () => ({
  useCreatePoseEndorsement: (_sceneId: string) => ({
    mutate: mockCreatePoseEndorsement,
    isPending: false,
  }),
  useDeletePoseEndorsement: (_sceneId: string) => ({
    mutate: mockDeletePoseEndorsement,
    isPending: false,
  }),
  useChangePoseEndorsement: (_sceneId: string) => ({
    mutate: mockChangePoseEndorsement,
    isPending: false,
  }),
  useAnswerPoseEndorsement: (_sceneId: string) => ({
    mutate: mockAnswerPoseEndorsement,
    isPending: false,
  }),
  useCreateSceneEntryEndorsement: (_sceneId: string) => ({
    mutate: mockCreateSceneEntryEndorsement,
    isPending: false,
  }),
  useCreateStyleEndorsement: (_sceneId: string) => ({
    mutate: mockCreateStyleEndorsement,
    ...styleMutationState,
  }),
}));

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

import { EndorsementControl } from '../EndorsementControl';

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

function makeInteraction(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 1,
    persona: { id: 10, name: 'Alice' },
    content: 'Alice enters.',
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
    pose_kind: 'entry',
    endorsee_sheet_id: 20,
    endorsable_resonances: [
      { id: 5, name: 'Courage' },
      { id: 6, name: 'Wisdom' },
    ],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests: kind="pose"
// ---------------------------------------------------------------------------

describe('EndorsementControl — kind="pose"', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an Endorse button', () => {
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="pose" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByRole('button', { name: /endorse/i })).toBeInTheDocument();
  });

  it('clicking Endorse lists every resonance under its affinity, not just endorsable_resonances', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="pose" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse/i }));
    await waitFor(() => {
      expect(screen.getByText('Primal')).toBeInTheDocument();
    });
    for (const name of ['Celestial', 'Abyssal', 'Fury', 'Grief', 'Mercy', 'Cruelty']) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.queryByText('Courage')).toBeNull();
  });

  it('selecting a resonance calls pose mutation with { interaction, resonance }', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="pose" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse/i }));
    await waitFor(() => screen.getByText('Grief'));
    await user.click(screen.getByText('Grief'));
    expect(mockCreatePoseEndorsement).toHaveBeenCalledWith({ interaction: 1, resonance: 42 });
  });

  it('still offers the menu when the poser holds nothing endorsable', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({ endorsable_resonances: [] })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByRole('button', { name: /endorse/i })).toBeInTheDocument();
  });

  it('shows the endorser a dashed waiting chip with Change and Withdraw, and no Endorse menu', async () => {
    const user = userEvent.setup();
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: { id: 7, resonance_id: 42, settled: false },
          pending_picks: [
            {
              endorsement_id: 7,
              resonance_id: 42,
              resonance_name: 'Grief',
              endorser_name: 'ViewerChar',
              mine: true,
              can_answer: false,
            },
          ],
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('pose-pick-waiting')).toHaveTextContent('Grief · waiting for Alice');
    expect(screen.getByTestId('pose-pick-waiting')).toHaveClass('border-dashed');
    expect(screen.queryByRole('button', { name: /^endorse/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();

    await user.click(screen.getByTestId('pose-pick-withdraw'));
    expect(mockDeletePoseEndorsement).toHaveBeenCalledWith(7);

    await user.click(screen.getByRole('button', { name: 'Change' }));
    await waitFor(() => screen.getByText('Mercy'));
    await user.click(screen.getByText('Mercy'));
    expect(mockChangePoseEndorsement).toHaveBeenCalledWith({ id: 7, resonance: 43 });
  });

  it('treats an endorsement row that waits as a waiting pick even before the picks arrive', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: {
            id: 7,
            resonance_id: 43,
            settled: false,
            awaiting_acceptance: true,
          },
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('pose-pick-waiting')).toHaveTextContent('Mercy · waiting for Alice');
    expect(screen.getByTestId('pose-pick-withdraw')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();
  });

  it('shows the poser who proposed what, with Accept and Decline and no Endorse menu', async () => {
    const user = userEvent.setup();
    // persona.id === 7 is the viewer's own persona: the poser reading her own pose.
    render(
      <EndorsementControl
        interaction={makeInteraction({
          persona: { id: 7, name: 'ViewerChar' },
          pending_picks: [
            {
              endorsement_id: 8,
              resonance_id: 43,
              resonance_name: 'Mercy',
              endorser_name: 'Ilsa',
              mine: false,
              can_answer: true,
            },
          ],
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('pose-pick-proposal-8')).toHaveTextContent('Ilsa proposed Mercy');
    expect(screen.queryByRole('button', { name: /^endorse/i })).toBeNull();

    await user.click(screen.getByTestId('pose-pick-accept-8'));
    expect(mockAnswerPoseEndorsement).toHaveBeenCalledWith({ id: 8, accept: true });
    await user.click(screen.getByTestId('pose-pick-decline-8'));
    expect(mockAnswerPoseEndorsement).toHaveBeenCalledWith({ id: 8, accept: false });
  });

  it('shows a pick the viewer may not answer as nothing at all', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({
          persona: { id: 7, name: 'ViewerChar' },
          pending_picks: [
            {
              endorsement_id: 8,
              resonance_id: 43,
              resonance_name: 'Mercy',
              endorser_name: 'Ilsa',
              mine: false,
              can_answer: false,
            },
          ],
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('withholds the menu once the pose carries a mark, undone or not', () => {
    const mark = {
      grant_id: 4,
      resonance_id: 44,
      resonance_name: 'Cruelty',
      act_label: 'Intimidated Hale',
      undone: false,
      undone_by: null,
      can_undo: false,
    };
    const { rerender } = render(
      <EndorsementControl
        interaction={makeInteraction({ act_marks: [mark] })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByRole('button', { name: /endorse/i })).toBeNull();

    rerender(
      <EndorsementControl
        interaction={makeInteraction({
          act_marks: [{ ...mark, undone: true, undone_by: 'gm' as const }],
        })}
        sceneId="1"
        kind="pose"
      />
    );
    // A GM's undo does not give the pose back: the server still refuses to endorse it.
    expect(screen.queryByRole('button', { name: /endorse/i })).toBeNull();
  });

  it('a reached pose offers its one resonance and sends no resonance', async () => {
    const user = userEvent.setup();
    render(
      <EndorsementControl
        interaction={makeInteraction({
          endorsable_resonances: [{ id: 5, name: 'Cruelty' }],
          reached_resonance: { id: 5, name: 'Cruelty' },
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    await user.click(screen.getByRole('button', { name: 'Endorse their Cruelty' }));
    expect(mockCreatePoseEndorsement).toHaveBeenCalledWith({ interaction: 1 });
  });

  it('shows endorsed state + retract affordance when my_pose_endorsement is set and settled=false', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: { id: 99, resonance_id: 5, settled: false },
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByRole('button', { name: /retract/i })).toBeInTheDocument();
  });

  it('retract button calls delete with endorsement id', async () => {
    const user = userEvent.setup();
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: { id: 99, resonance_id: 5, settled: false },
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    await user.click(screen.getByRole('button', { name: /retract/i }));
    expect(mockDeletePoseEndorsement).toHaveBeenCalledWith(99);
  });

  it('retract is disabled when settled=true', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: { id: 99, resonance_id: 5, settled: true },
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByRole('button', { name: /retract/i })).toBeDisabled();
  });

  it('renders pose_endorsers badges', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          pose_endorsers: [
            { persona_id: 11, persona_name: 'Bob', thumbnail_url: '', resonance_id: 5 },
          ],
        })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTitle('Bob endorsed with Courage')).toBeInTheDocument();
  });

  it('hides when the pose belongs to the viewer (self-pose)', () => {
    // persona.id === 7 which is the viewer's primary_persona_id
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ persona: { id: 7, name: 'ViewerChar' } })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides for whisper mode', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ mode: 'whisper' })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides for very_private visibility', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ visibility: 'very_private' })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Tests: kind="entry"
// ---------------------------------------------------------------------------

describe('EndorsementControl — kind="entry"', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an Endorse entry button', () => {
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="entry" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByRole('button', { name: /endorse entry/i })).toBeInTheDocument();
  });

  it('selecting a resonance calls entry mutation with { endorsee_sheet, scene, resonance }', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="entry" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse entry/i }));
    await waitFor(() => screen.getByText('Courage'));
    await user.click(screen.getByText('Courage'));
    expect(mockCreateSceneEntryEndorsement).toHaveBeenCalledWith({
      endorsee_sheet: 20,
      scene: 1,
      resonance: 5,
    });
  });

  it('shows entry_endorsers badges', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          entry_endorsers: [
            { persona_id: 12, persona_name: 'Carol', thumbnail_url: '', resonance_id: 6 },
          ],
        })}
        sceneId="1"
        kind="entry"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTitle('Carol endorsed with Wisdom')).toBeInTheDocument();
  });

  it('does NOT show a retract button for entry endorsements', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({
          my_pose_endorsement: { id: 99, resonance_id: 5, settled: false },
        })}
        sceneId="1"
        kind="entry"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();
  });

  it('hides entirely when endorsable_resonances is empty', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ endorsable_resonances: [] })}
        sceneId="1"
        kind="entry"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows endorsed indicator (not picker) when entry_endorsed_by_me=true', () => {
    render(
      <EndorsementControl
        interaction={makeInteraction({ entry_endorsed_by_me: true })}
        sceneId="1"
        kind="entry"
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('entry-endorsed-indicator')).toBeInTheDocument();
    // No "Endorse entry" button — endorsement is permanent, no retract.
    expect(screen.queryByRole('button', { name: /endorse entry/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();
  });

  it('hides and fires no mutation when endorsee_sheet_id is null (safe null guard)', async () => {
    // endorsee_sheet_id is typed number | null; the component must not cast it
    // unsafely when null — it should return null instead of firing a bad mutation.
    const user = userEvent.setup();
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ endorsee_sheet_id: null })}
        sceneId="1"
        kind="entry"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
    // No mutation should have been attempted.
    expect(mockCreateSceneEntryEndorsement).not.toHaveBeenCalled();
    // Suppress unused variable warning — user is needed for async setup but no interaction fires.
    void user;
  });
});

// ---------------------------------------------------------------------------
// Tests: kind="style" (#2031)
// ---------------------------------------------------------------------------

describe('EndorsementControl — kind="style"', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    styleMutationState = { isPending: false, isSuccess: false, isError: false, error: null };
  });

  it('shows an Endorse style button', () => {
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByRole('button', { name: /endorse style/i })).toBeInTheDocument();
  });

  it('clicking Endorse style opens a picker listing endorsable_resonances', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse style/i }));
    await waitFor(() => {
      expect(screen.getByText('Courage')).toBeInTheDocument();
      expect(screen.getByText('Wisdom')).toBeInTheDocument();
    });
  });

  it('selecting a resonance calls style mutation with { endorsee_sheet, scene, resonance }', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse style/i }));
    await waitFor(() => screen.getByText('Courage'));
    await user.click(screen.getByText('Courage'));
    expect(mockCreateStyleEndorsement).toHaveBeenCalledWith({
      endorsee_sheet: 20,
      scene: 1,
      resonance: 5,
    });
  });

  it('does NOT show a retract button for style endorsements', () => {
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();
  });

  it('hides entirely when endorsable_resonances is empty', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ endorsable_resonances: [] })}
        sceneId="1"
        kind="style"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides for whisper mode', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ mode: 'whisper' })}
        sceneId="1"
        kind="style"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides for very_private visibility', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ visibility: 'very_private' })}
        sceneId="1"
        kind="style"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides and fires no mutation when endorsee_sheet_id is null (safe null guard)', async () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ endorsee_sheet_id: null })}
        sceneId="1"
        kind="style"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
    expect(mockCreateStyleEndorsement).not.toHaveBeenCalled();
  });

  it('shows an endorsed indicator (not the picker) once the style mutation succeeds', () => {
    styleMutationState = { isPending: false, isSuccess: true, isError: false, error: null };
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('style-endorsed-indicator')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /endorse style/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /retract/i })).toBeNull();
  });

  it('surfaces the backend error message verbatim when the style mutation fails', () => {
    styleMutationState = {
      isPending: false,
      isSuccess: false,
      isError: true,
      error: new Error('You are not wearing a bound style.'),
    };
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="style" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('You are not wearing a bound style.')).toBeInTheDocument();
  });
});
