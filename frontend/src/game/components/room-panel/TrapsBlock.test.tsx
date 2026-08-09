import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { toast } from 'sonner';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useRoomTrapsQuery } from '@/room_features/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { TrapsBlock } from './TrapsBlock';

vi.mock('@/room_features/queries', () => ({
  useRoomTrapsQuery: vi.fn(),
  roomTrapKeys: { forCharacter: (id: number) => ['room-features', 'traps', id] },
}));

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockUseRoomTrapsQuery = vi.mocked(useRoomTrapsQuery);
const mockUseDispatchPlayerAction = vi.mocked(useDispatchPlayerAction);

function mockDispatch(mutate = vi.fn()) {
  mockUseDispatchPlayerAction.mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  return mutate;
}

describe('TrapsBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the query is disabled (no active character)', () => {
    mockUseRoomTrapsQuery.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);
    mockDispatch();

    const { container } = renderWithProviders(<TrapsBlock characterId={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the trap list is empty', () => {
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);
    mockDispatch();

    const { container } = renderWithProviders(<TrapsBlock characterId={42} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders visible armed traps with a Disarm button', () => {
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [{ id: 5, name: 'Spike Pit', is_armed: true }],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);
    mockDispatch();

    renderWithProviders(<TrapsBlock characterId={42} />);

    expect(screen.getByText('Spike Pit')).toBeInTheDocument();
    expect(screen.getByTestId('trap-disarm-5')).toBeInTheDocument();
  });

  it('does not render a Disarm button for an already-disarmed trap', () => {
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [{ id: 5, name: 'Spike Pit', is_armed: false }],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);
    mockDispatch();

    renderWithProviders(<TrapsBlock characterId={42} />);

    expect(screen.getByText('Spike Pit')).toBeInTheDocument();
    expect(screen.queryByTestId('trap-disarm-5')).not.toBeInTheDocument();
  });

  it('dispatches disarm_trap with the trap id on Disarm click', async () => {
    const user = userEvent.setup();
    const mutate = mockDispatch();
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [{ id: 5, name: 'Spike Pit', is_armed: true }],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);

    renderWithProviders(<TrapsBlock characterId={42} />);

    await user.click(screen.getByTestId('trap-disarm-5'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'disarm_trap' },
          kwargs: { trap_id: 5 },
        },
        expect.any(Object)
      );
    });
  });

  it('surfaces a failed disarm consequence message via an error toast', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onSuccess({
        backend: 'registry',
        deferred: false,
        success: false,
        message: 'You trigger Spike Pit while trying to disarm it!',
      });
    });
    mockDispatch(mutate);
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [{ id: 5, name: 'Spike Pit', is_armed: true }],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);

    renderWithProviders(<TrapsBlock characterId={42} />);

    await user.click(screen.getByTestId('trap-disarm-5'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('You trigger Spike Pit while trying to disarm it!');
    });
  });

  it('surfaces a successful disarm message via a success toast', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_payload, options) => {
      options.onSuccess({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'You disarm Spike Pit.',
      });
    });
    mockDispatch(mutate);
    mockUseRoomTrapsQuery.mockReturnValue({
      data: [{ id: 5, name: 'Spike Pit', is_armed: true }],
    } as unknown as ReturnType<typeof useRoomTrapsQuery>);

    renderWithProviders(<TrapsBlock characterId={42} />);

    await user.click(screen.getByTestId('trap-disarm-5'));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('You disarm Spike Pit.');
    });
  });
});
