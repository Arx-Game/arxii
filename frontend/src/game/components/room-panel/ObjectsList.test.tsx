/**
 * #3044 — ObjectsList tests.
 *
 * Verifies: rows expand and dispatch the `look` registry action with the
 * object's int pk (dbref parsed via `dbrefToId`) exactly once, the returned
 * description renders on success, and a board-flagged row offers a
 * "View Board" button that mounts `MissionBoardDialog`.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useDispatchPlayerAction } from '@/combat/queries';
import { useBoardPostings, useTakeBoardPosting } from '@/missions/queries';
import type { RoomStateObject } from '@/hooks/types';
import { ObjectsList } from './ObjectsList';

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(),
}));

vi.mock('@/missions/queries', async () => {
  const actual = await vi.importActual<typeof import('@/missions/queries')>('@/missions/queries');
  return {
    ...actual,
    useBoardPostings: vi.fn(),
    useTakeBoardPosting: vi.fn(),
  };
});

const mockUseDispatchPlayerAction = vi.mocked(useDispatchPlayerAction);
const mockUseBoardPostings = vi.mocked(useBoardPostings);
const mockUseTakeBoardPosting = vi.mocked(useTakeBoardPosting);

function mockDispatch(mutate = vi.fn(), isPending = false) {
  mockUseDispatchPlayerAction.mockReturnValue({
    mutate,
    isPending,
  } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  return mutate;
}

const barrel: RoomStateObject = {
  dbref: '#100',
  name: 'a wooden barrel',
  thumbnail_url: null,
  commands: [],
};

const board: RoomStateObject = {
  dbref: '#200',
  name: 'a notice board',
  thumbnail_url: null,
  commands: [],
  is_mission_board: true,
};

describe('ObjectsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseBoardPostings.mockReturnValue({
      isLoading: false,
      data: { count: 0, results: [] },
    } as unknown as ReturnType<typeof useBoardPostings>);
    mockUseTakeBoardPosting.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTakeBoardPosting>);
  });

  it('renders nothing when there are no objects', () => {
    mockDispatch();
    const { container } = renderWithProviders(<ObjectsList objects={[]} characterId={7} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('dispatches look with the object pk on expand and renders the result', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_body: unknown, opts?: { onSuccess?: (r: unknown) => void }) => {
      opts?.onSuccess?.({ success: true, message: 'A sturdy oak barrel.' });
    });
    mockDispatch(mutate);

    renderWithProviders(<ObjectsList objects={[barrel]} characterId={7} />);

    await user.click(screen.getByTestId('examine-toggle-#100'));

    expect(mutate).toHaveBeenCalledWith(
      {
        ref: { backend: 'registry', registry_key: 'look' },
        kwargs: { target: 100 },
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    );
    await waitFor(() => {
      expect(screen.getByTestId('examine-text-#100')).toHaveTextContent('A sturdy oak barrel.');
    });
  });

  it('does not re-dispatch on a second expand of the same row', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_body: unknown, opts?: { onSuccess?: (r: unknown) => void }) => {
      opts?.onSuccess?.({ success: true, message: 'A sturdy oak barrel.' });
    });
    mockDispatch(mutate);

    renderWithProviders(<ObjectsList objects={[barrel]} characterId={7} />);

    await user.click(screen.getByTestId('examine-toggle-#100'));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    // Collapse then re-expand — cached text, no second dispatch.
    await user.click(screen.getByTestId('examine-toggle-#100'));
    await user.click(screen.getByTestId('examine-toggle-#100'));

    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('shows a "View Board" button only for objects flagged is_mission_board', () => {
    mockDispatch();
    renderWithProviders(<ObjectsList objects={[barrel, board]} characterId={7} />);

    expect(screen.queryByTestId('open-board-#100')).not.toBeInTheDocument();
    expect(screen.getByTestId('open-board-#200')).toBeInTheDocument();
  });

  it('opens MissionBoardDialog for the board object id when "View Board" is clicked', async () => {
    const user = userEvent.setup();
    mockDispatch();

    renderWithProviders(<ObjectsList objects={[board]} characterId={7} />);

    await user.click(screen.getByTestId('open-board-#200'));

    const dialog = screen.getByTestId('mission-board-dialog');
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText('a notice board')).toBeInTheDocument();
  });
});
