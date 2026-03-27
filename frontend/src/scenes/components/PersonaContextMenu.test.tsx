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

import { PersonaContextMenu } from './PersonaContextMenu';

const MOCK_ACTIONS: AvailableActionsResponse = {
  self_actions: [],
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

function createWrapper(prePopulate = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  // Pre-populate the cache since PersonaContextMenu reads from cache only
  if (prePopulate) {
    queryClient.setQueryData(['available-actions', '1'], MOCK_ACTIONS);
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
