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

const MOCK_ACTIONS: AvailableActionsResponse = {
  self_actions: [
    {
      key: 'perform',
      name: 'Perform',
      icon: 'drama',
      category: 'self',
      techniques: [],
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
  ],
  technique_actions: [],
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

  it('shows "No actions available" when lists are empty', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      self_actions: [],
      targeted_actions: [],
      technique_actions: [],
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
