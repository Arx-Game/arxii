import { render, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SummonPromptNotifier } from '../SummonPromptNotifier';

const mockUseSummonOfferInbox = vi.fn();
const mockUseDispatchPlayerAction = vi.fn();
const mockMutateAsync = vi.fn();
vi.mock('../queries', () => ({
  useSummonOfferInbox: (...args: unknown[]) => mockUseSummonOfferInbox(...args),
}));
vi.mock('@/combat/queries', () => ({
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

function offer(id: number, gmName = 'Story Weaver') {
  return {
    id,
    target_character_id: 42,
    gm_display_name: gmName,
    scene_title: 'A Quiet Word',
    created_at: '2026-08-08T00:00:00Z',
  };
}

describe('SummonPromptNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSummonOfferInbox.mockReturnValue({ data: [], isLoading: false });
    mockRosterEntries = [{ id: 1, name: 'TestChar', character_id: 42, primary_persona_id: 77 }];
  });

  it('fires a custom toast the first time a new pending offer appears', () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(1)], isLoading: false });

    render(<SummonPromptNotifier />);

    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('does not re-fire for an offer id already toasted', () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(1)], isLoading: false });

    const { rerender } = render(<SummonPromptNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);

    rerender(<SummonPromptNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('names the GM and scene only, never room contents', () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(1)], isLoading: false });
    render(<SummonPromptNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));

    expect(getByTestId('summon-prompt-toast')).toHaveTextContent('Story Weaver');
    expect(getByTestId('summon-prompt-toast')).toHaveTextContent('A Quiet Word');
  });

  it('Accept button dispatches accept_gm_summon and dismisses on success', async () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({});
    render(<SummonPromptNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('summon-toast-accept-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'accept_gm_summon' },
        kwargs: {},
      });
    });
    await waitFor(() => {
      expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
    });
  });

  it('Decline button dispatches decline_gm_summon and dismisses on success', async () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({});
    render(<SummonPromptNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('summon-toast-decline-btn'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'decline_gm_summon' },
        kwargs: {},
      });
    });
    await waitFor(() => {
      expect(toastDismissMock).toHaveBeenCalledWith('toast-1');
    });
  });

  it('shows an inline error and does not dismiss on a business-rule rejection', async () => {
    mockUseSummonOfferInbox.mockReturnValue({ data: [offer(5)], isLoading: false });
    mockMutateAsync.mockResolvedValue({ success: false, message: 'No pending summon.' });
    render(<SummonPromptNotifier />);

    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));
    fireEvent.click(getByTestId('summon-toast-accept-btn'));

    await waitFor(() => {
      expect(getByTestId('summon-toast-error')).toHaveTextContent('No pending summon.');
    });
    expect(toastDismissMock).not.toHaveBeenCalled();
  });
});
