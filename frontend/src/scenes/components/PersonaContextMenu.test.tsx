import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { PlayerActionsResponse } from '../actionTypes';

vi.mock('../actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
  createActionRequest: vi.fn(),
}));

// Mock the roster query — component resolves active character → characterId
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: null,
        active_persona_id: null,
      },
    ],
  })),
}));

// Mock the Redux selector — return the active character name used above
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

// Mock the combat dispatch hook (challenge affordance, #1181; identify affordance, #1107)
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({
    mutateAsync: vi.fn(() => Promise.resolve()),
    isPending: false,
  })),
  combatKeys: { duelChallengesAll: () => ['combat', 'duel-challenges'] },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { PersonaContextMenu } from './PersonaContextMenu';
import { createActionRequest, fetchAvailableActions } from '../actionQueries';
import { useDispatchPlayerAction } from '@/combat/queries';

function makeAction(
  overrides: Partial<PlayerActionsResponse['results'][0]> = {}
): PlayerActionsResponse['results'][0] {
  return {
    backend: 'registry',
    display_name: 'Test Action',
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: 'test_action',
    },
    target_spec: null,
    enhancements: [],
    strain: null,
    ...overrides,
  };
}

const MOCK_ACTIONS: PlayerActionsResponse = {
  count: 2,
  next: null,
  previous: null,
  results: [
    makeAction({
      display_name: 'Intimidate',
      ref: {
        backend: 'registry',
        challenge_instance_id: null,
        approach_id: null,
        technique_id: null,
        registry_key: 'intimidate',
      },
    }),
    makeAction({
      display_name: 'Persuade',
      ref: {
        backend: 'registry',
        challenge_instance_id: null,
        approach_id: null,
        technique_id: null,
        registry_key: 'persuade',
      },
    }),
  ],
};

// The cache key is now ['available-actions', characterId] where characterId=42
// from the mocked useMyRosterEntriesQuery above.
function createWrapper(prePopulate = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  // Pre-populate the cache since PersonaContextMenu reads from cache only
  if (prePopulate) {
    queryClient.setQueryData(['available-actions', 42], MOCK_ACTIONS);
  }
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

interface ScenePersonaStub {
  id: number;
  name: string;
  character_sheet?: number;
  allow_social_actions?: boolean;
}

// Wrapper that also seeds the scene cache (['scene', sceneId]) so the challenge
// affordance can resolve the target persona's character + opt-out state (#1181).
function createWrapperWithScene(personas: ScenePersonaStub[], prePopulateActions = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  if (prePopulateActions) {
    queryClient.setQueryData(['available-actions', 42], MOCK_ACTIONS);
  }
  queryClient.setQueryData(['scene', '1'], { id: 1, personas });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('PersonaContextMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows targeted actions in the context menu', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    // With pre-populated cache, the button should render immediately
    expect(screen.getByRole('button')).toBeInTheDocument();

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });
    expect(screen.getByText('Persuade')).toBeInTheDocument();
  });

  it('shows "Attach to Pose" section when onAttachAction is provided', async () => {
    const user = userEvent.setup();
    const onAttachAction = vi.fn();

    render(
      <PersonaContextMenu
        personaId={10}
        personaName="Alice"
        sceneId="1"
        onAttachAction={onAttachAction}
      >
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toBeInTheDocument();

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Attach to Pose')).toBeInTheDocument();
    });
  });

  it('calls onAttachAction with persona name as target', async () => {
    const user = userEvent.setup();
    const onAttachAction = vi.fn();

    render(
      <PersonaContextMenu
        personaId={10}
        personaName="Alice"
        sceneId="1"
        onAttachAction={onAttachAction}
      >
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toBeInTheDocument();

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Attach to Pose')).toBeInTheDocument();
    });

    // The "Attach to Pose" section has its own copies of the actions
    const attachItems = screen.getAllByText('Intimidate');
    // Click the one in the "Attach to Pose" section (second occurrence)
    await user.click(attachItems[attachItems.length - 1]);

    expect(onAttachAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'intimidate',
        name: 'Intimidate',
        target: 'Alice',
        requiresTarget: true,
        targetPersonaId: 10,
      })
    );
  });

  // Radix submenu interaction is keyboard-driven in jsdom (hover grace-area
  // math needs real pointer coordinates). ArrowDown focuses the first action,
  // ArrowRight opens its submenu with the first entry (Default) focused.
  async function openIntimidateSubmenu() {
    const user = userEvent.setup();
    vi.mocked(createActionRequest).mockResolvedValue({ status: 'resolved' });
    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );
    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate');
    await user.keyboard('{ArrowDown}{ArrowRight}');
    await screen.findByText(/^Default/);
    return user;
  }

  it('fires the action with whisper delivery from the submenu (#903)', async () => {
    const user = await openIntimidateSubmenu();
    // Default → Openly → Subtly (target only)
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '1',
        expect.objectContaining({
          action_key: 'intimidate',
          target_persona_id: 10,
          delivery: 'whisper',
        })
      );
    });
  });

  it('fires the default entry with no delivery so the backend resolves it (#903)', async () => {
    const user = await openIntimidateSubmenu();
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '1',
        expect.objectContaining({ action_key: 'intimidate', delivery: undefined })
      );
    });
  });

  // ---------------------------------------------------------------------------
  // Challenge to a duel affordance (#1181)
  // ---------------------------------------------------------------------------

  it('dispatches the challenge action with the target persona id when clicked', async () => {
    const user = userEvent.setup();
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      // Target persona belongs to character 99 (≠ viewer 42), social actions allowed.
      { wrapper: createWrapperWithScene([{ id: 10, name: 'Alice', character_sheet: 99 }]) }
    );

    await user.click(screen.getByRole('button'));
    const challengeItem = await screen.findByTestId('challenge-to-duel-item');
    await user.click(challengeItem);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'challenge' },
      kwargs: { target: 10 },
    });
  });

  it('hides the challenge item when the target has opted out of social targeting', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      {
        wrapper: createWrapperWithScene([
          { id: 10, name: 'Alice', character_sheet: 99, allow_social_actions: false },
        ]),
      }
    );

    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate'); // menu is open (other actions present)
    expect(screen.queryByTestId('challenge-to-duel-item')).not.toBeInTheDocument();
  });

  it('hides the challenge item for the viewer’s own persona (no self-duel)', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="TestChar" sceneId="1">
        <span>TestChar</span>
      </PersonaContextMenu>,
      // character_sheet 42 == the viewer's character_id from the roster mock.
      { wrapper: createWrapperWithScene([{ id: 10, name: 'TestChar', character_sheet: 42 }]) }
    );

    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate');
    expect(screen.queryByTestId('challenge-to-duel-item')).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Identify affordance (#1107 Task 3 review — Critical finding: identify must
  // dispatch via the registry REST path, never the createActionRequest consent
  // pipeline the targetedActions submenu below uses).
  // ---------------------------------------------------------------------------

  it('dispatches the identify action via the registry dispatch hook with the target persona id', async () => {
    const user = userEvent.setup();
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true, message: 'ok' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapperWithScene([{ id: 10, name: 'Alice', character_sheet: 99 }]) }
    );

    await user.click(screen.getByRole('button'));
    const identifyItem = await screen.findByTestId('identify-persona-item');
    await user.click(identifyItem);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'identify' },
      kwargs: { target: 10 },
    });
  });

  it('shows the identify item even when the target has opted out of social targeting', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      {
        wrapper: createWrapperWithScene([
          { id: 10, name: 'Alice', character_sheet: 99, allow_social_actions: false },
        ]),
      }
    );

    await user.click(screen.getByRole('button'));
    expect(await screen.findByTestId('identify-persona-item')).toBeInTheDocument();
  });

  it('hides the identify item for the viewer’s own persona (no self-identify)', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="TestChar" sceneId="1">
        <span>TestChar</span>
      </PersonaContextMenu>,
      { wrapper: createWrapperWithScene([{ id: 10, name: 'TestChar', character_sheet: 42 }]) }
    );

    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate');
    expect(screen.queryByTestId('identify-persona-item')).not.toBeInTheDocument();
  });

  it('does not show "Attach to Pose" section when onAttachAction is not provided', async () => {
    const user = userEvent.setup();

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toBeInTheDocument();

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });

    expect(screen.queryByText('Attach to Pose')).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Consistency with ActionPanel (#2158)
  // ---------------------------------------------------------------------------

  it('shows an unmet-prerequisite action disabled with its reason, not omitted (#2158)', async () => {
    const user = userEvent.setup();
    // Same action-object shape ActionPanel.test.tsx's disabled-tooltip test exercises.
    const actionsWithUnmet: PlayerActionsResponse = {
      count: 1,
      next: null,
      previous: null,
      results: [
        makeAction({
          display_name: 'Intimidate',
          prerequisite_met: false,
          prerequisite_reasons: ['Must be in combat'],
          ref: {
            backend: 'registry',
            challenge_instance_id: null,
            approach_id: null,
            technique_id: null,
            registry_key: 'intimidate',
          },
        }),
      ],
    };
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    queryClient.setQueryData(['available-actions', 42], actionsWithUnmet);

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        ),
      }
    );
    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });
    const item = screen.getByText('Intimidate').closest('[role="menuitem"], button');
    expect(item).toHaveAttribute('title', expect.stringContaining('Must be in combat'));
    expect(item).toBeDisabled();
  });

  it('fetches available actions itself, not only from a pre-populated cache (#2158)', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      // No pre-populated cache — the opposite of every other test in this file.
      { wrapper: createWrapper(false) }
    );
    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });
    // Proves the component's own fetch populated the menu, not a
    // pre-existing cache entry.
    expect(fetchAvailableActions).toHaveBeenCalledWith(42);
  });
});
