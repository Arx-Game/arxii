import { render, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { DuelWithdrawNotifier } from '../DuelWithdrawNotifier';

const mockUseDuelChallengeInbox = vi.fn();
const mockUseDispatchPlayerAction = vi.fn();
const mockMutateAsync = vi.fn();
vi.mock('@/combat/queries', () => ({
  useDuelChallengeInbox: (...args: unknown[]) => mockUseDuelChallengeInbox(...args),
  useDispatchPlayerAction: (characterId: number) => {
    mockUseDispatchPlayerAction(characterId);
    return { mutateAsync: mockMutateAsync, isPending: false };
  },
}));

let mockRosterEntries: unknown[] = [
  { id: 1, name: 'TestChar', character_id: 42, primary_persona_id: 77 },
];
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({ data: mockRosterEntries }),
}));

const toastCustomMock = vi.fn();
const toastDismissMock = vi.fn();
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    custom: (...args: unknown[]) => toastCustomMock(...args),
    dismiss: (...args: unknown[]) => toastDismissMock(...args),
  }),
}));

function outgoingChallenge(id: number, challengedName = 'Rivalis') {
  return {
    id,
    challenger: { id: 42, name: 'TestChar' },
    challenged: { id: 900 + id, name: challengedName },
    status: 'pending' as const,
    is_lethal: false,
    opponent_name: '',
    opponent_tier: '',
    created_at: '2026-07-11T00:00:00Z',
    resolved_at: null,
    resulting_encounter: null,
  };
}

describe('DuelWithdrawNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDuelChallengeInbox.mockReturnValue({ data: [], isLoading: false });
    mockRosterEntries = [{ id: 1, name: 'TestChar', character_id: 42, primary_persona_id: 77 }];
  });

  it('polls the outgoing role, scoped to the caller played characters', () => {
    render(<DuelWithdrawNotifier />);

    expect(mockUseDuelChallengeInbox).toHaveBeenCalledWith(
      expect.objectContaining({ role: 'outgoing' })
    );
  });

  it('fires a persistent (duration: Infinity) toast for a new outgoing challenge', () => {
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(1)],
      isLoading: false,
    });

    render(<DuelWithdrawNotifier />);

    expect(toastCustomMock).toHaveBeenCalledTimes(1);
    expect(toastCustomMock).toHaveBeenCalledWith(expect.any(Function), { duration: Infinity });
  });

  it('does not re-fire for a challenge id already toasted', () => {
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(1)],
      isLoading: false,
    });

    const { rerender } = render(<DuelWithdrawNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);

    rerender(<DuelWithdrawNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('dismisses the toast automatically once the challenge drops out of the poll', () => {
    toastCustomMock.mockReturnValue('toast-1');
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(1)],
      isLoading: false,
    });

    const { rerender } = render(<DuelWithdrawNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);

    // Challenge accepted/declined/expired on the other side — drops out of the
    // outgoing PENDING poll without the player clicking Withdraw here.
    mockUseDuelChallengeInbox.mockReturnValue({ data: [], isLoading: false });
    rerender(<DuelWithdrawNotifier />);

    expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
  });

  it('Withdraw dispatches registry_key "withdraw" with the correct challenge_id', async () => {
    toastCustomMock.mockReturnValue('toast-1');
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(5)],
      isLoading: false,
    });
    mockMutateAsync.mockResolvedValue({});

    render(<DuelWithdrawNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-withdraw-toast-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'withdraw' },
        kwargs: { challenge_id: 5 },
      });
    });
    await waitFor(() => {
      expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
    });
  });

  it('dispatches as the challenger (background) character, not the active one', async () => {
    mockRosterEntries = [
      { id: 1, name: 'CharA', character_id: 42, primary_persona_id: 77 },
      { id: 2, name: 'CharB', character_id: 99, primary_persona_id: 88 },
    ];
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [
        {
          id: 7,
          challenger: { id: 99, name: 'CharB' },
          challenged: { id: 900, name: 'Rivalis' },
          status: 'pending' as const,
          created_at: '2026-07-11T00:00:00Z',
          resolved_at: null,
          resulting_encounter: null,
        },
      ],
      isLoading: false,
    });
    mockMutateAsync.mockResolvedValue({});

    render(<DuelWithdrawNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId, getByText } = render(renderFn('toast-1'));

    // Resolved against B's roster entry, never the active character (A, id 42).
    expect(mockUseDispatchPlayerAction).toHaveBeenCalledWith(99);
    expect(mockUseDispatchPlayerAction).not.toHaveBeenCalledWith(42);
    expect(getByText(/Issued as/)).toHaveTextContent('Issued as CharB.');

    fireEvent.click(getByTestId('duel-withdraw-toast-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'withdraw' },
        kwargs: { challenge_id: 7 },
      });
    });
  });

  it('shows an inline error and does not dismiss the toast when the dispatch fails', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(5)],
      isLoading: false,
    });
    mockMutateAsync.mockRejectedValue(new Error('Network error'));
    render(<DuelWithdrawNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-withdraw-toast-btn'));

    await waitFor(() => {
      expect(getByTestId('duel-withdraw-toast-error')).toHaveTextContent('Network error');
    });
    expect(toastDismissMock).not.toHaveBeenCalled();
  });

  it('shows an inline error and does not dismiss the toast on success:false (#2423)', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [outgoingChallenge(5)],
      isLoading: false,
    });
    mockMutateAsync.mockResolvedValue({ success: false, message: 'Already resolved.' });
    render(<DuelWithdrawNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-withdraw-toast-btn'));

    await waitFor(() => {
      expect(getByTestId('duel-withdraw-toast-error')).toHaveTextContent('Already resolved.');
    });
    expect(toastDismissMock).not.toHaveBeenCalled();
  });
});
