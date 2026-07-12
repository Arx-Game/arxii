import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { setActiveSession, startSession } from '@/store/gameSlice';
import type { IncomingConsentRequest } from '../actionTypes';

const {
  mockDispatch,
  mockConnect,
  mockNavigate,
  mockFetchIncomingConsentRequests,
  toastMock,
  sessionsRef,
  rosterEntriesRef,
} = vi.hoisted(() => ({
  mockDispatch: vi.fn(),
  mockConnect: vi.fn(),
  mockNavigate: vi.fn(),
  mockFetchIncomingConsentRequests: vi.fn(),
  toastMock: vi.fn(),
  sessionsRef: { current: {} as Record<string, { isConnected: boolean }> },
  rosterEntriesRef: { current: [] as unknown[] },
}));

vi.mock('@/store/hooks', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({ game: { sessions: sessionsRef.current } }),
}));

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ connect: mockConnect }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({ data: rosterEntriesRef.current }),
}));

vi.mock('../actionQueries', () => ({
  fetchIncomingConsentRequests: (...args: unknown[]) => mockFetchIncomingConsentRequests(...args),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(toastMock, { error: vi.fn(), success: vi.fn() }),
}));

import { ConsentAttentionNotifier } from './ConsentAttentionNotifier';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function request(overrides: Partial<IncomingConsentRequest> = {}): IncomingConsentRequest {
  return {
    id: 1,
    scene: 55,
    target_persona: 22,
    target_name: 'CharB',
    initiator_name: 'Rivalis',
    action_key: 'intimidate',
    technique_name: null,
    created_at: '2026-07-11T00:00:00Z',
    ...overrides,
  };
}

describe('ConsentAttentionNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionsRef.current = {};
    rosterEntriesRef.current = [
      { id: 1, name: 'CharA', character_id: 1, primary_persona_id: 11, active_persona_id: 11 },
      { id: 2, name: 'CharB', character_id: 2, primary_persona_id: 22, active_persona_id: 22 },
    ];
    mockFetchIncomingConsentRequests.mockResolvedValue({ results: [] });
  });

  it('fires a toast naming the resolved (background) character, action, and initiator', async () => {
    mockFetchIncomingConsentRequests.mockResolvedValue({ results: [request()] });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        'Consent request for CharB: intimidate from Rivalis',
        expect.objectContaining({ action: expect.objectContaining({ label: 'View' }) })
      );
    });
  });

  it('prefers technique_name over action_key when present', async () => {
    mockFetchIncomingConsentRequests.mockResolvedValue({
      results: [request({ id: 2, technique_name: 'Mind Whisper' })],
    });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        'Consent request for CharB: Mind Whisper from Rivalis',
        expect.anything()
      );
    });
  });

  it('resolves the target via active_persona_id when it does not match primary_persona_id', async () => {
    // CharB is currently wearing a mask (active_persona_id=99) that differs
    // from their primary (22) — the request is addressed to the worn mask.
    rosterEntriesRef.current = [
      { id: 2, name: 'CharB', character_id: 2, primary_persona_id: 22, active_persona_id: 99 },
    ];
    mockFetchIncomingConsentRequests.mockResolvedValue({
      results: [request({ id: 6, target_persona: 99 })],
    });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        'Consent request for CharB: intimidate from Rivalis',
        expect.anything()
      );
    });
  });

  it('falls back to the raw target_name when no roster entry matches', async () => {
    rosterEntriesRef.current = [
      { id: 1, name: 'CharA', character_id: 1, primary_persona_id: 11, active_persona_id: 11 },
    ];
    mockFetchIncomingConsentRequests.mockResolvedValue({
      results: [request({ id: 7, target_persona: 999, target_name: 'Mystery Mask' })],
    });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        'Consent request for Mystery Mask: intimidate from Rivalis',
        expect.anything()
      );
    });
  });

  it('does not re-fire for a request id already toasted', async () => {
    mockFetchIncomingConsentRequests.mockResolvedValue({ results: [request({ id: 3 })] });

    const { rerender } = render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });
    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1));

    rerender(<ConsentAttentionNotifier />);
    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1));
  });

  it('clicking the toast action starts a session for a not-yet-live character and navigates to /game', async () => {
    mockFetchIncomingConsentRequests.mockResolvedValue({ results: [request({ id: 4 })] });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });
    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1));

    const [, options] = toastMock.mock.calls[0] as [string, { action: { onClick: () => void } }];
    options.action.onClick();

    expect(mockDispatch).toHaveBeenCalledWith(startSession('CharB'));
    expect(mockConnect).toHaveBeenCalledWith('CharB');
    expect(mockNavigate).toHaveBeenCalledWith('/game');
  });

  it('clicking the toast action switches an already-live character without restarting it', async () => {
    sessionsRef.current = { CharB: { isConnected: true } };
    mockFetchIncomingConsentRequests.mockResolvedValue({ results: [request({ id: 5 })] });

    render(<ConsentAttentionNotifier />, { wrapper: createWrapper() });
    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1));

    const [, options] = toastMock.mock.calls[0] as [string, { action: { onClick: () => void } }];
    options.action.onClick();

    expect(mockDispatch).toHaveBeenCalledWith(setActiveSession('CharB'));
    expect(mockDispatch).not.toHaveBeenCalledWith(startSession('CharB'));
    expect(mockConnect).not.toHaveBeenCalled();
  });
});
