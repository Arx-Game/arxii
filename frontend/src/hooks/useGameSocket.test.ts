import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// No existing test file/harness covered useGameSocket.ts before this task (verified:
// no useGameSocket.test.ts existed, and the only other test that touches this hook,
// game/GamePage.test.tsx, mocks the whole hook away rather than exercising it). This
// harness follows the vi.hoisted + per-module vi.mock convention already used for
// hooks with the same dependency shape (e.g.
// scenes/components/ConsentAttentionNotifier.test.tsx's `@/store/hooks` /
// `react-router-dom` mocks) and adds a minimal mock WebSocket to drive the
// connect/close/message lifecycle useGameSocket.ts actually listens for.

const { mockDispatch, mockNavigate } = vi.hoisted(() => ({
  mockDispatch: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock('@/store/hooks', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({ auth: { account: { id: 1, username: 'tester' } } }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('@/config', () => ({
  getWebSocketUrl: () => 'ws://test.invalid/ws/game/',
}));

vi.mock('@/evennia_replacements/api', () => ({
  fetchAccount: vi.fn(),
}));

vi.mock('@/queryClient', () => ({
  queryClient: { invalidateQueries: vi.fn(() => Promise.resolve()) },
}));

const { mockFetchPoseSubmission } = vi.hoisted(() => ({
  mockFetchPoseSubmission: vi.fn(),
}));

vi.mock('@/scenes/queries', () => ({
  fetchPoseSubmission: mockFetchPoseSubmission,
}));

import { useGameSocket, __resetGameSocketModuleStateForTests } from './useGameSocket';
import { queryClient } from '@/queryClient';
import { draftStorageKey, type Draft } from '@/game/useDraftStore';

type Listener = (event: unknown) => void;

/**
 * Minimal mock WebSocket: enough of the constructor/addEventListener/send
 * surface for useGameSocket.ts's connect() to drive, plus a `dispatch` helper
 * tests use to simulate the server pushing open/close/message frames. Kept in
 * this file (rather than a shared fixture) since this is the first test to
 * exercise useGameSocket.ts directly.
 */
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState = 0;
  url: string;
  sent: string[] = [];
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  addEventListener(type: string, callback: Listener): void {
    (this.listeners[type] ??= []).push(callback);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  dispatch(type: string, event: unknown = {}): void {
    (this.listeners[type] ?? []).forEach((callback) => callback(event));
  }
}

/** Seeds a `pending`/`unknown` draft directly in sessionStorage, the format
 * `reconcileStoredDrafts` (useGameSocket.ts's reconnect-open handler) scans. */
function seedStoredDraft(overrides: Partial<Draft> & { clientRequestId: string }): void {
  const key = draftStorageKey({ accountId: 1, personaId: 7, conversationKey: 'room:1' });
  const draft: Draft = {
    content: 'Silas waves.',
    languageId: null,
    recipients: [],
    replyTo: null,
    companion: false,
    attachment: null,
    status: 'pending',
    rejectionReason: null,
    mode: null,
    ...overrides,
  };
  sessionStorage.setItem(key, JSON.stringify(draft));
}

describe('useGameSocket connection generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    // useGameSocket.ts keeps its connection bookkeeping (sockets, reconnect
    // attempts/timers, generations) at module scope, not per-hook-instance -
    // without this, a socket or pending reconnect timer left over from a
    // previous test case would silently leak into the next one.
    __resetGameSocketModuleStateForTests();
    sessionStorage.clear();
    mockFetchPoseSubmission.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('increments the generation number on each connect() for the same character', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Gen-One';

    await act(async () => {
      await result.current.connect(character);
    });
    expect(result.current.currentGeneration(character)).toBe(1);

    const firstSocket = MockWebSocket.instances[0];
    // Explicit (normal) disconnect frees the character for a fresh connect().
    act(() => {
      firstSocket.dispatch('close', { code: 1000 });
    });

    await act(async () => {
      await result.current.connect(character);
    });
    expect(result.current.currentGeneration(character)).toBe(2);
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('discards a message delivered on a connection superseded by a reconnect', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Gen-Two';

    await act(async () => {
      await result.current.connect(character);
    });
    expect(result.current.currentGeneration(character)).toBe(1);
    const staleSocket = MockWebSocket.instances[0];

    // Abnormal close (not code 1000) triggers the automatic-reconnect path.
    act(() => {
      staleSocket.dispatch('close', { code: 1006 });
    });

    // First backoff delay is 1000ms; advancing past it fires the reconnect's
    // connect() call, which (since the mocked account is already present)
    // runs synchronously through to creating the new socket.
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.currentGeneration(character)).toBe(2);
    expect(MockWebSocket.instances).toHaveLength(2);

    const dispatchCallsBeforeStaleMessage = mockDispatch.mock.calls.length;

    // A message arrives late on the now-superseded first socket - it must be
    // discarded before it reaches any state update (e.g. addSessionMessage).
    act(() => {
      staleSocket.dispatch('message', { data: JSON.stringify(['text', ['hi'], {}]) });
    });

    expect(mockDispatch.mock.calls.length).toBe(dispatchCallsBeforeStaleMessage);
  });
});

/** Resolves/rejects on demand — lets a test hold a lookup call open mid-flight. */
function createDeferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/**
 * How many `game/setSessionConnectionStatus` actions with `status: true`
 * `mockDispatch` has seen so far — the abnormal-close path also dispatches
 * this action type (with `status: false`), so the payload must be checked
 * too, not just the action type.
 */
function readyDispatchCount(): number {
  return mockDispatch.mock.calls.filter(([action]) => {
    const typed = action as { type?: string; payload?: { status?: boolean } };
    return typed?.type === 'game/setSessionConnectionStatus' && typed.payload?.status === true;
  }).length;
}

describe('useGameSocket reconnect reconciliation ordering (#3760 Task 12)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    __resetGameSocketModuleStateForTests();
    sessionStorage.clear();
    mockFetchPoseSubmission.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('reauthorizes (re-puppets) immediately, then reconciles a stranded draft, and only then flips ready / invalidates the room-snapshot query', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Reconcile-One';
    seedStoredDraft({ clientRequestId: 'req-1', status: 'pending', content: 'Silas waves.' });

    const deferred = createDeferred<{ interaction_id: number; replayed: boolean } | null>();
    mockFetchPoseSubmission.mockReturnValueOnce(deferred.promise);

    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.dispatch('open');
    });

    // Reauthorize: the puppet text is sent immediately, before reconciliation
    // is even asked to start.
    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0])).toEqual(['text', [`@ic ${character}`], {}]);

    // Reconcile: the lookup for the stranded draft has been dispatched...
    expect(mockFetchPoseSubmission).toHaveBeenCalledWith('req-1');
    // ...but it hasn't resolved yet, so readiness must not have flipped and
    // the room-snapshot query must not have been invalidated.
    expect(readyDispatchCount()).toBe(0);
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();

    // The lookup resolves: the send had actually landed.
    await act(async () => {
      deferred.resolve({ interaction_id: 42, replayed: false });
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Only now does readiness flip and the feed get invalidated.
    expect(readyDispatchCount()).toBe(1);
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['scene-interactions'],
    });

    // The stranded draft was reconciled (cleared) since the lookup found it.
    const stored = sessionStorage.getItem(
      draftStorageKey({ accountId: 1, personaId: 7, conversationKey: 'room:1' })
    );
    expect(stored && (JSON.parse(stored) as Draft).status).toBe('clean');
  });

  it('discards a reauthorization/reconciliation that completes after this generation has been superseded by a fresh reconnect', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Reconcile-Two';
    seedStoredDraft({ clientRequestId: 'req-stale', status: 'unknown', content: 'Silas waves.' });

    const staleDeferred = createDeferred<{ interaction_id: number; replayed: boolean } | null>();
    // First lookup call (generation 1, slow) hangs; second call (generation
    // 2's own reconciliation of the same still-pending stored draft)
    // resolves immediately so generation 2 can reach Ready.
    mockFetchPoseSubmission.mockReturnValueOnce(staleDeferred.promise).mockResolvedValueOnce(null);

    await act(async () => {
      await result.current.connect(character);
    });
    const staleSocket = MockWebSocket.instances[0];
    expect(result.current.currentGeneration(character)).toBe(1);

    act(() => {
      staleSocket.dispatch('open');
    });
    expect(mockFetchPoseSubmission).toHaveBeenCalledTimes(1);
    expect(readyDispatchCount()).toBe(0);

    // Generation 1's connection drops abnormally before its reconciliation
    // resolves, and the automatic reconnect supersedes it.
    act(() => {
      staleSocket.dispatch('close', { code: 1006 });
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.currentGeneration(character)).toBe(2);
    const freshSocket = MockWebSocket.instances[1];

    act(() => {
      freshSocket.dispatch('open');
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Generation 2 reconciled (its own lookup resolved immediately) and
    // reached Ready.
    expect(readyDispatchCount()).toBe(1);
    const invalidateCallsAfterGenTwo = (queryClient.invalidateQueries as ReturnType<typeof vi.fn>)
      .mock.calls.length;
    expect(invalidateCallsAfterGenTwo).toBeGreaterThan(0);

    // Generation 1's stale reauthorization/reconciliation finally resolves —
    // it must be discarded, not flip readiness again.
    await act(async () => {
      staleDeferred.resolve({ interaction_id: 1, replayed: false });
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(readyDispatchCount()).toBe(1);
    expect((queryClient.invalidateQueries as ReturnType<typeof vi.fn>).mock.calls.length).toBe(
      invalidateCallsAfterGenTwo
    );
  });
});
