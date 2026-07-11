import { render } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { DuelChallengeNotifier } from '../DuelChallengeNotifier';

const mockUseDuelChallengeInbox = vi.fn();
const mockMutate = vi.fn();
vi.mock('@/combat/queries', () => ({
  useDuelChallengeInbox: (...args: unknown[]) => mockUseDuelChallengeInbox(...args),
  useDispatchPlayerAction: () => ({ mutate: mockMutate, isPending: false }),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({
    data: [{ id: 1, name: 'TestChar', character_id: 42, primary_persona_id: 77 }],
  }),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' } }),
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

    // Same data on a re-render (e.g. the 15s poll ticking with no change).
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

  it('Accept button dispatches the accept registry action with the challenge id', () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-accept-btn'));

    expect(mockMutate).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'accept' },
      kwargs: { challenge_id: 5 },
    });
    expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
  });

  it('Decline button dispatches the decline registry action with the challenge id', () => {
    mockUseDuelChallengeInbox.mockReturnValue({ data: [challenge(5)], isLoading: false });
    render(<DuelChallengeNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('duel-toast-decline-btn'));

    expect(mockMutate).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'decline' },
      kwargs: { challenge_id: 5 },
    });
    expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
  });
});
