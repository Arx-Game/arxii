import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { AvailableActionsResponse } from '../actionTypes';

vi.mock('../actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
  createActionRequest: vi.fn(),
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

const MOCK_ACTIONS: AvailableActionsResponse = {
  self_actions: [
    {
      key: 'perform',
      name: 'Perform',
      icon: 'drama',
      category: 'self',
      techniques: [],
    },
    {
      key: 'entrance',
      name: 'Entrance',
      icon: 'sparkles',
      category: 'self',
      techniques: [
        { id: 1, name: 'Grand Entry', capability_type: 'presence', capability_value: 3 },
      ],
    },
  ],
  targeted_actions: [
    {
      key: 'intimidate',
      name: 'Intimidate',
      icon: 'shield_alert',
      category: 'social',
      techniques: [],
    },
    {
      key: 'persuade',
      name: 'Persuade',
      icon: 'handshake',
      category: 'social',
      techniques: [],
    },
  ],
  technique_actions: [],
};

describe('ActionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders self-targeted actions after opening the panel', async () => {
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
    expect(screen.getByText('Your Actions')).toBeInTheDocument();
  });

  it('renders targeted social actions', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });
    expect(screen.getByText('Persuade')).toBeInTheDocument();
    expect(screen.getByText('Social Actions')).toBeInTheDocument();
  });

  it('clicking a self-targeted action calls createActionRequest', async () => {
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
      expect(createActionRequest).toHaveBeenCalledWith('42', {
        action_key: 'perform',
        technique_id: undefined,
      });
    });
  });

  it('clicking a self-targeted action with techniques includes technique_id', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    vi.mocked(createActionRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Entrance')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Entrance'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith('42', {
        action_key: 'entrance',
        technique_id: 1,
      });
    });
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

  it('shows "No actions available" when all action lists are empty', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      self_actions: [],
      targeted_actions: [],
      technique_actions: [],
    });
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('No actions available.')).toBeInTheDocument();
    });
  });

  it('clicking a targeted action shows target selection UI', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Intimidate'));

    await waitFor(() => {
      expect(screen.getByText('Select a target for: Intimidate')).toBeInTheDocument();
    });
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('clicking Cancel in target selection returns to main panel', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue(MOCK_ACTIONS);
    const user = userEvent.setup();

    render(<ActionPanel sceneId="42" />, { wrapper: createWrapper() });

    const trigger = screen.getByRole('button');
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByText('Intimidate')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Intimidate'));

    await waitFor(() => {
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Cancel'));

    // Should be back to the main trigger button, not showing target selection
    await waitFor(() => {
      expect(screen.queryByText('Select a target for: Intimidate')).not.toBeInTheDocument();
    });
  });
});
