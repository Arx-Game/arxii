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

import { PersonaContextMenu } from './PersonaContextMenu';
import { createActionRequest } from '../actionQueries';

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

  it('fires the action with whisper delivery from the submenu (#903)', async () => {
    const user = userEvent.setup();
    vi.mocked(createActionRequest).mockResolvedValue(
      {} as Awaited<ReturnType<typeof createActionRequest>>
    );

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate');
    // Radix submenu interaction is keyboard-driven in jsdom (hover grace-area
    // math needs real pointer coordinates). ArrowDown focuses the first action,
    // ArrowRight opens its submenu on the first entry (Default), two more
    // ArrowDowns reach "Subtly (target only)" (Default → Openly → Subtly).
    await user.keyboard('{ArrowDown}{ArrowRight}');
    await screen.findByText('Subtly (target only)');
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
    const user = userEvent.setup();
    vi.mocked(createActionRequest).mockResolvedValue(
      {} as Awaited<ReturnType<typeof createActionRequest>>
    );

    render(
      <PersonaContextMenu personaId={10} personaName="Alice" sceneId="1">
        <span>Alice</span>
      </PersonaContextMenu>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button'));
    await screen.findByText('Intimidate');
    // ArrowRight opens the submenu with the first entry (Default) focused.
    await user.keyboard('{ArrowDown}{ArrowRight}');
    await screen.findByText(/^Default/);
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '1',
        expect.objectContaining({ action_key: 'intimidate', delivery: undefined })
      );
    });
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
});
