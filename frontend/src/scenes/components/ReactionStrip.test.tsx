import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ReactionWindowPayload } from '../types';

vi.mock('../queries', () => ({
  reactToWindow: vi.fn(),
  reactToInteraction: vi.fn(),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
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
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

import { ReactionStrip } from './ReactionStrip';
import { reactToWindow, reactToInteraction } from '../queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';

const INTERACTION_ID = 99;

function makeWindow(overrides: Partial<ReactionWindowPayload> = {}): ReactionWindowPayload {
  return {
    id: 5,
    kind: 'entrance',
    is_open: true,
    public: true,
    choices: [
      { slug: '11', label: 'Moonlight' },
      { slug: '12', label: 'Thorns' },
    ],
    reactions: [{ persona_id: 9, persona_name: 'Bel', choice: '11' }],
    counts: { '11': 1 },
    my_reaction: null,
    ...overrides,
  };
}

function makeKudosWindow(overrides: Partial<ReactionWindowPayload> = {}): ReactionWindowPayload {
  return {
    id: 6,
    kind: 'kudos',
    is_open: true,
    public: true,
    choices: [{ slug: 'kudos', label: 'Kudos' }],
    reactions: [],
    counts: {},
    my_reaction: null,
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('ReactionStrip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useMyRosterEntriesQuery).mockReturnValue({
      data: [
        {
          id: 1,
          name: 'TestChar',
          character_id: 42,
          profile_picture_url: null,
          primary_persona_id: 7,
          active_persona_id: 7,
        },
      ],
    } as never);
  });

  it('renders a chip per choice with counts', () => {
    render(<ReactionStrip windows={[makeWindow()]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Moonlight 1')).toBeInTheDocument();
    expect(screen.getByText('Thorns')).toBeInTheDocument();
  });

  it('fires the mutation with the chosen slug', async () => {
    const user = userEvent.setup();
    vi.mocked(reactToWindow).mockResolvedValue(undefined);
    render(<ReactionStrip windows={[makeWindow()]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByText('Thorns'));
    await waitFor(() => {
      expect(reactToWindow).toHaveBeenCalledWith(5, { persona_id: 7, choice: '12' });
    });
  });

  it('disables chips once the viewer has reacted', () => {
    render(
      <ReactionStrip
        windows={[makeWindow({ my_reaction: '11' })]}
        sceneId="1"
        interactionId={INTERACTION_ID}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('Moonlight 1')).toBeDisabled();
    expect(screen.getByText('Thorns')).toBeDisabled();
  });

  it('settled windows render read-only with a closed note', () => {
    render(
      <ReactionStrip
        windows={[makeWindow({ is_open: false })]}
        sceneId="1"
        interactionId={INTERACTION_ID}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('(scene closed)')).toBeInTheDocument();
    expect(screen.getByText('Moonlight 1')).toBeDisabled();
  });

  // --- First-kudos chip (#2031) ---------------------------------------

  it('renders a kudos chip when no kudos window exists yet, even with no windows at all', () => {
    render(<ReactionStrip windows={[]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('reaction-strip')).toBeInTheDocument();
    expect(screen.getByText('Kudos')).toBeInTheDocument();
  });

  it('does not render a duplicate kudos chip when an open kudos window exists', () => {
    render(
      <ReactionStrip windows={[makeKudosWindow()]} sceneId="1" interactionId={INTERACTION_ID} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getAllByText('Kudos')).toHaveLength(1);
  });

  it('POSTs the exact kudos body via reactToInteraction on click', async () => {
    const user = userEvent.setup();
    vi.mocked(reactToInteraction).mockResolvedValue(undefined);
    render(<ReactionStrip windows={[]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByText('Kudos'));
    await waitFor(() => {
      expect(reactToInteraction).toHaveBeenCalledWith({
        persona_id: 7,
        interaction_id: INTERACTION_ID,
        kind: 'kudos',
        choice: 'kudos',
      });
    });
  });

  it('disables the kudos chip when no persona is resolved', () => {
    vi.mocked(useMyRosterEntriesQuery).mockReturnValue({ data: [] } as never);
    render(<ReactionStrip windows={[]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Kudos')).toBeDisabled();
  });

  it('surfaces the 400 detail message when the kudos POST fails', async () => {
    const user = userEvent.setup();
    vi.mocked(reactToInteraction).mockRejectedValue(new Error('Already gave kudos on this pose.'));
    render(<ReactionStrip windows={[]} sceneId="1" interactionId={INTERACTION_ID} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByText('Kudos'));
    await waitFor(() => {
      expect(screen.getByText('Already gave kudos on this pose.')).toBeInTheDocument();
    });
  });
});
