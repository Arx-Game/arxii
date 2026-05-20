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

import { fetchAvailableActions } from '../actionQueries';
import { ActionAttachment } from './ActionAttachment';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

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
    ...overrides,
  };
}

const MOCK_ACTIONS: PlayerActionsResponse = {
  count: 2,
  next: null,
  previous: null,
  results: [
    makeAction({
      display_name: 'Perform',
      ref: {
        backend: 'registry',
        challenge_instance_id: null,
        approach_id: null,
        technique_id: null,
        registry_key: 'perform',
      },
    }),
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
  ],
};

describe('ActionAttachment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the attach action button', () => {
    render(
      <ActionAttachment sceneId="1" attachment={null} onAttach={vi.fn()} onDetach={vi.fn()} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByRole('button', { name: 'Attach action' })).toBeInTheDocument();
  });

  it('opens popover and shows action list on click', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();

    render(
      <ActionAttachment sceneId="1" attachment={null} onAttach={vi.fn()} onDetach={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: 'Attach action' }));

    await waitFor(() => {
      expect(screen.getByText('Perform')).toBeInTheDocument();
    });
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
  });

  it('calls onAttach when an action is selected', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();
    const onAttach = vi.fn();

    render(
      <ActionAttachment sceneId="1" attachment={null} onAttach={onAttach} onDetach={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: 'Attach action' }));

    await waitFor(() => {
      expect(screen.getByText('Perform')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Perform'));

    expect(onAttach).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'perform',
        name: 'Perform',
        requiresTarget: false,
      })
    );
  });

  it('shows chip when action is attached', () => {
    render(
      <ActionAttachment
        sceneId="1"
        attachment={{
          actionKey: 'intimidate',
          name: 'Intimidate',
          requiresTarget: true,
          target: 'Bob',
        }}
        onAttach={vi.fn()}
        onDetach={vi.fn()}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Intimidate')).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
  });

  it('calls onDetach when clicking the chip', async () => {
    const user = userEvent.setup();
    const onDetach = vi.fn();

    render(
      <ActionAttachment
        sceneId="1"
        attachment={{
          actionKey: 'intimidate',
          name: 'Intimidate',
          requiresTarget: true,
          target: 'Bob',
        }}
        onAttach={vi.fn()}
        onDetach={onDetach}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: 'Detach action' }));

    expect(onDetach).toHaveBeenCalled();
  });

  it('calls onDetach when clicking the zap button while action is attached', async () => {
    const user = userEvent.setup();
    const onDetach = vi.fn();

    render(
      <ActionAttachment
        sceneId="1"
        attachment={{
          actionKey: 'perform',
          name: 'Perform',
          requiresTarget: false,
        }}
        onAttach={vi.fn()}
        onDetach={onDetach}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: 'Attach action' }));

    expect(onDetach).toHaveBeenCalled();
  });

  it('shows "No actions available" when list is empty', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    const user = userEvent.setup();

    render(
      <ActionAttachment sceneId="1" attachment={null} onAttach={vi.fn()} onDetach={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: 'Attach action' }));

    await waitFor(() => {
      expect(screen.getByText('No actions available')).toBeInTheDocument();
    });
  });

  it('shows "(select target)" when targeted action has no target', () => {
    render(
      <ActionAttachment
        sceneId="1"
        attachment={{
          actionKey: 'intimidate',
          name: 'Intimidate',
          requiresTarget: true,
        }}
        onAttach={vi.fn()}
        onDetach={vi.fn()}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('(select target)')).toBeInTheDocument();
  });
});
