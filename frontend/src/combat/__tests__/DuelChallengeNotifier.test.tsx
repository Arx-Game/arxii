import { render, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { DuelChallengeNotifier } from '../DuelChallengeNotifier';

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

function challenge(id: number, challengerName = 'Rivalis') {
  return {
    id,
    challenger: { id: 900 + id, name: challengerName },
    challenged: { id: 42, name: 'TestChar' },
    status: 'pending' as const,
    created_at: '2026-07-11T00:00:00Z',
    resolved_at: null,
    resulting_encounter: null,
  };
}

describe('DuelChallengeNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDuelChallengeInbox.mockReturnValue({ data: [], isLoading: false });
    mockRosterEntries = [{ id: 1, name: 'TestChar', character_id: 42, primary_persona_id: 77 }];
  });

  it('fires a custom toast the first time a new incoming challenge appears', () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(1)], isLoading: false });

    render(<DuelChallengeNotifier />);

    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('does not re-fire for a challenge id already toasted', () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(1)], isLoading: false });

    const { rerender } = render(<DuelChallengeNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);

    rerender(<DuelChallengeNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('fires a second toast for a genuinely new second challenge id', () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(1)], isLoading: false });
    const { rerender } = render(<DuelChallengeNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);

    mockUseDuelChallengeInbox.mockReturnValue({
      data: [challenge(1), challenge(2)],
      isLoading: false,
    });
    rerender(<DuelChallengeNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(2);
  });

  it('Accept button dispatches the accept registry action and dismisses on success', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({});
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-accept-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'accept' },
        kwargs: { challenge_id: 5 },
      });
    });
    await waitFor(() => {
      expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
    });
  });

  it('Decline button dispatches the decline registry action and dismisses on success', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({});
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-decline-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'decline' },
        kwargs: { challenge_id: 5 },
      });
    });
    await waitFor(() => {
      expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
    });
  });

  it('dispatches as the challenged (background) character, not the active one', async () => {
    mockRosterEntries = [
      { id: 1, name: 'CharA', character_id: 42, primary_persona_id: 77 },
      { id: 2, name: 'CharB', character_id: 99, primary_persona_id: 88 },
    ];
    mockUseDuelChallengeInbox.mockReturnValue({
      data: [
        {
          id: 7,
          challenger: { id: 900, name: 'Rivalis' },
          challenged: { id: 99, name: 'CharB' },
          status: 'pending' as const,
          created_at: '2026-07-11T00:00:00Z',
          resolved_at: null,
          resulting_encounter: null,
        },
      ],
      isLoading: false,
    });
    mockMutateAsync.mockResolvedValue({});

    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId, getByText } = render(renderFn('toast-1'));

    // Resolved against B's roster entry, never the active character (A, id 42).
    expect(mockUseDispatchPlayerAction).toHaveBeenCalledWith(99);
    expect(mockUseDispatchPlayerAction).not.toHaveBeenCalledWith(42);
    expect(getByText(/Responding as/)).toHaveTextContent('Responding as CharB.');

    fireEvent.click(getByTestId('duel-toast-accept-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'accept' },
        kwargs: { challenge_id: 7 },
      });
    });
  });

  it('shows an inline error and does not dismiss the toast when the dispatch fails', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    mockMutateAsync.mockRejectedValue(new Error('Network error'));
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-accept-btn'));

    await waitFor(() => {
      expect(getByTestId('duel-toast-error')).toHaveTextContent('Network error');
    });
    expect(toastDismissMock).not.toHaveBeenCalled();
    expect(getByTestId('duel-toast-accept-btn')).not.toBeDisabled();
  });

  it('shows an inline error and does not dismiss the toast when the dispatch resolves success:false (#2423)', async () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({ success: false, message: 'Challenge already expired.' });
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-accept-btn'));

    await waitFor(() => {
      expect(getByTestId('duel-toast-error')).toHaveTextContent('Challenge already expired.');
    });
    expect(toastDismissMock).not.toHaveBeenCalled();
  });
});
