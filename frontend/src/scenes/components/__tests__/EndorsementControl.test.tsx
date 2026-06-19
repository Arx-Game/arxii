/**
 * Tests for EndorsementControl (#1138) — resonance-picker + endorsement badge strip
 * for both pose and scene-entry endorsements.
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
const mockCreateSceneEntryEndorsement = vi.fn();

vi.mock('../../queries', () => ({
  useCreatePoseEndorsement: (_sceneId: string) => ({
    mutate: mockCreatePoseEndorsement,
    isPending: false,
  }),
  useDeletePoseEndorsement: (_sceneId: string) => ({
    mutate: mockDeletePoseEndorsement,
    isPending: false,
  }),
  useCreateSceneEntryEndorsement: (_sceneId: string) => ({
    mutate: mockCreateSceneEntryEndorsement,
    isPending: false,
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

  it('clicking Endorse opens a picker listing endorsable_resonances', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="pose" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse/i }));
    await waitFor(() => {
      expect(screen.getByText('Courage')).toBeInTheDocument();
      expect(screen.getByText('Wisdom')).toBeInTheDocument();
    });
  });

  it('selecting a resonance calls pose mutation with { interaction, resonance }', async () => {
    const user = userEvent.setup();
    render(<EndorsementControl interaction={makeInteraction()} sceneId="1" kind="pose" />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /endorse/i }));
    await waitFor(() => screen.getByText('Courage'));
    await user.click(screen.getByText('Courage'));
    expect(mockCreatePoseEndorsement).toHaveBeenCalledWith({ interaction: 1, resonance: 5 });
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

  it('hides entirely when endorsable_resonances is empty', () => {
    const { container } = render(
      <EndorsementControl
        interaction={makeInteraction({ endorsable_resonances: [] })}
        sceneId="1"
        kind="pose"
      />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toBeNull();
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
