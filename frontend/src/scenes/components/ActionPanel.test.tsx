import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { PlayerActionsResponse } from '../actionTypes';

vi.mock('../actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
  fetchSceneActions: vi.fn(() => Promise.resolve([])),
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

import { fetchAvailableActions, createActionRequest } from '../actionQueries';
import { ActionPanel } from './ActionPanel';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// Minimal PlayerAction factory
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
  count: 3,
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
      display_name: 'Entrance',
      ref: {
        backend: 'registry',
        challenge_instance_id: null,
        approach_id: null,
        technique_id: 1,
        registry_key: 'entrance',
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

describe('ActionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders actions after opening the panel', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    // Click the trigger button to open the popover
    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Perform')).toBeInTheDocument();
    });
    expect(screen.getByText('Entrance')).toBeInTheDocument();
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
  });

  it('shows loading state while fetching actions', async () => {
    // Never resolve so we stay in loading state
    vi.mocked(fetchAvailableActions).mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  it('shows "No actions available" when action list is empty', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('No actions available.')).toBeInTheDocument();
    });
  });

  it('clicking an action calls createActionRequest', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    vi.mocked(createActionRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Perform')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Perform'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '42',
        expect.objectContaining({
          action_key: 'perform',
        })
      );
    });
  });
});
