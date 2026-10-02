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

const { mockToast } = vi.hoisted(() => ({
  mockToast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

vi.mock('sonner', () => ({
  toast: mockToast,
}));

import {
  PAGE_RESUME_CLOSE_CODE,
  useGameSocket,
  __resetGameSocketModuleStateForTests,
} from './useGameSocket';
import { queryClient } from '@/queryClient';
import { draftStorageKey, type Draft } from '@/game/useDraftStore';
import { recordedUnknownFrames, __resetUnknownFramesForTests } from './unknownFrames';

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

  /** Records the caller's intent only; a test dispatches the resulting
   * `close` event itself, the way a real socket fires it asynchronously.
   *
   * Rejects a close code the way a browser does: anything other than 1000 or
   * 3000-4999 throws `InvalidAccessError` and leaves the socket open. A mock
   * that accepted any code hid #4026, where `close(1001)` threw inside a
   * try/catch and every wake resume leaked a live socket. A reason longer
   * than 123 UTF-8 bytes throws `SyntaxError`, as it does in a browser.
   * `failClose` makes a test's socket throw on close whatever it is given. */
  closed = false;
  closeCode: number | undefined;
  failClose = false;
  close(code?: number, reason?: string): void {
    if (code !== undefined && code !== 1000 && (code < 3000 || code > 4999)) {
      throw new DOMException(
        `Failed to execute 'close' on 'WebSocket': The close code must be either 1000, ` +
          `or between 3000 and 4999. ${code} is neither.`,
        'InvalidAccessError'
      );
    }
    if (reason !== undefined && new TextEncoder().encode(reason).length > 123) {
      throw new DOMException(
        "Failed to execute 'close' on 'WebSocket': The close reason must not be greater " +
          'than 123 UTF-8 bytes.',
        'SyntaxError'
      );
    }
    if (this.failClose) {
      throw new DOMException('close failed', 'InvalidStateError');
    }
    this.closed = true;
    this.closeCode = code;
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

describe('useGameSocket wake resume (#3933)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    __resetGameSocketModuleStateForTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('replaces a stale suspended socket and ignores its late close event', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Wake-Resume';

    await act(async () => {
      await result.current.connect(character);
    });
    const staleSocket = MockWebSocket.instances[0];

    act(() => {
      result.current.resume(character);
    });

    // The replaced socket really closes (#4026): with a code the browser
    // rejects, close() throws and the socket stays open behind the new one.
    expect(staleSocket.closed).toBe(true);
    expect(staleSocket.closeCode).toBe(PAGE_RESUME_CLOSE_CODE);
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(MockWebSocket.instances.filter((socket) => !socket.closed)).toHaveLength(1);
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionConnectionStatus',
      payload: { character, status: false },
    });
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionLifecycle',
      payload: { character, lifecycleState: 'reconnecting' },
    });

    act(() => {
      staleSocket.dispatch('close', { code: PAGE_RESUME_CLOSE_CODE });
    });
    expect(mockDispatch).not.toHaveBeenCalledWith({ type: 'game/resetGame', payload: undefined });
  });

  it('still replaces the socket, and reports it, when close() throws', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result } = renderHook(() => useGameSocket());
    const character = 'Wake-Resume-Throw';

    await act(async () => {
      await result.current.connect(character);
    });
    const staleSocket = MockWebSocket.instances[0];
    staleSocket.failClose = true;

    act(() => {
      result.current.resume(character);
    });

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(warn).toHaveBeenCalledWith(
      '[socket] wake resume could not close the replaced socket',
      expect.any(DOMException)
    );
    warn.mockRestore();
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

/** Delivers the protocol milestones required before a socket is application-ready. */
function dispatchReadiness(socket: MockWebSocket, character: string): void {
  socket.dispatch('message', {
    data: JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 1, character_id: 42, character_name: character },
    ]),
  });
  socket.dispatch('message', {
    data: JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#1', name: 'The Room' },
        characters: [],
        objects: [],
        exits: [],
      },
    ]),
  });
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

    // Reauthorize: the puppet frame is sent immediately, before reconciliation
    // is even asked to start.
    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0])).toEqual(['puppet', [], { character }]);
    dispatchReadiness(socket, character);

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
    dispatchReadiness(freshSocket, character);
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

describe('useGameSocket disconnect (#3818 "Leave the world")', () => {
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

  it('closes only that character, forgets its session, and never reconnects it', async () => {
    const { result } = renderHook(() => useGameSocket());

    await act(async () => {
      await result.current.connect('Aria');
      await result.current.connect('Bram');
    });
    const [ariaSocket, bramSocket] = MockWebSocket.instances;

    act(() => {
      result.current.disconnect('Aria');
    });

    expect(ariaSocket.closed).toBe(true);
    expect(bramSocket.closed).toBe(false);
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'game/endSession', payload: 'Aria' });

    // Even an abnormal-looking close is local because disconnect() marked the
    // socket before calling close(); Bram is still in the world, and Aria is
    // never resurrected.
    act(() => {
      ariaSocket.dispatch('close', { code: 1006 });
    });
    expect(mockDispatch).not.toHaveBeenCalledWith({ type: 'game/resetGame', payload: undefined });
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('cancels a pending reconnect for that character', async () => {
    const { result } = renderHook(() => useGameSocket());

    await act(async () => {
      await result.current.connect('Aria');
    });
    const ariaSocket = MockWebSocket.instances[0];
    // An abnormal close arms the backoff reconnect...
    act(() => {
      ariaSocket.dispatch('close', { code: 1006 });
    });

    // ...which leaving the world on purpose must cancel.
    act(() => {
      result.current.disconnect('Aria');
    });
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });
});

describe('useGameSocket typed quit', () => {
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

  // The server closes the socket for a typed `quit` with code 1000 and the
  // command's own reason. The code alone is a remote close like any other
  // (#4007 reconnects those); the reason is the server saying the player left.
  it.each(['quit', 'quit/all'])(
    'a close the server gives the reason %s for leaves the world and never reconnects',
    async (reason) => {
      const { result } = renderHook(() => useGameSocket());
      await act(async () => {
        await result.current.connect('Aria');
      });
      const socket = MockWebSocket.instances[0];

      act(() => {
        socket.dispatch('close', { code: 1000, reason });
      });

      expect(mockDispatch).toHaveBeenCalledWith({ type: 'game/endSession', payload: 'Aria' });
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'game/resetGame', payload: undefined });
      expect(mockDispatch).not.toHaveBeenCalledWith({
        type: 'game/setSessionLifecycle',
        payload: { character: 'Aria', lifecycleState: 'reconnecting' },
      });
      expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['account'] });
      expect(mockNavigate).toHaveBeenCalledWith('/hall');

      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      expect(MockWebSocket.instances).toHaveLength(1);
    }
  );

  it('leaves another character in the world', async () => {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
      await result.current.connect('Bram');
    });
    const [ariaSocket] = MockWebSocket.instances;

    act(() => {
      ariaSocket.dispatch('close', { code: 1000, reason: 'quit' });
    });

    expect(mockDispatch).toHaveBeenCalledWith({ type: 'game/endSession', payload: 'Aria' });
    expect(mockDispatch).not.toHaveBeenCalledWith({ type: 'game/endSession', payload: 'Bram' });
    expect(mockDispatch).not.toHaveBeenCalledWith({ type: 'game/resetGame', payload: undefined });
  });

  it('still reconnects a normal close that carries any other reason', async () => {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });

    act(() => {
      MockWebSocket.instances[0].dispatch('close', { code: 1000, reason: 'idle timeout' });
      vi.advanceTimersByTime(1000);
    });

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

describe('useGameSocket remote close recovery (#4007)', () => {
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

  it.each([1000, 1001, 1006])('reconnects a remote close code %s', async (code) => {
    const { result } = renderHook(() => useGameSocket());
    const character = `Remote-${code}`;
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.dispatch('close', { code });
    });
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('stops retrying after a puppet refusal', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Refused';
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.dispatch('message', {
        data: JSON.stringify(['command_error', [], { command: 'puppet', error: 'Refused.' }]),
      });
      socket.dispatch('close', { code: 1006 });
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionLifecycle',
      payload: { character, lifecycleState: 'entry-error' },
    });
  });

  it('does not reset retry accounting on open without readiness', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Not-Ready';
    await act(async () => {
      await result.current.connect(character);
    });

    // A transport open and completed backfill are not enough: the puppet and
    // room-state milestones are intentionally absent.
    act(() => {
      MockWebSocket.instances[0].dispatch('open');
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(readyDispatchCount()).toBe(0);

    act(() => {
      MockWebSocket.instances[0].dispatch('close', { code: 1000 });
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    act(() => {
      MockWebSocket.instances[1].dispatch('open');
      MockWebSocket.instances[1].dispatch('close', { code: 1000 });
    });
    // The second close is attempt 2, not attempt 1 again.
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionLifecycle',
      payload: { character, lifecycleState: 'reconnecting' },
    });
  });

  it('caps retries and enters an actionable error after exhaustion', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Exhausted';
    await act(async () => {
      await result.current.connect(character);
    });

    const delays = [1000, 2000, 4000, 8000, 16000, 30000];
    for (const delay of delays) {
      const socket = MockWebSocket.instances.at(-1) as MockWebSocket;
      act(() => {
        socket.dispatch('close', { code: 1006 });
        vi.advanceTimersByTime(delay);
      });
    }
    expect(MockWebSocket.instances).toHaveLength(7);

    act(() => {
      MockWebSocket.instances.at(-1)?.dispatch('close', { code: 1006 });
    });
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionLifecycle',
      payload: { character, lifecycleState: 'entry-error' },
    });
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(7);
  });
});

describe('useGameSocket text frames become feed notes (#3856)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-14T22:00:00.000Z'));
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

  function dispatchedTypes(): string[] {
    return mockDispatch.mock.calls.map(([action]) => (action as { type: string }).type);
  }

  function noteDispatches(): unknown[] {
    return mockDispatch.mock.calls
      .map(([action]) => action as { type?: string; payload?: unknown })
      .filter((action) => action.type === 'game/addFeedNote')
      .map((action) => action.payload);
  }

  async function deliver(frame: unknown): Promise<void> {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    act(() => {
      MockWebSocket.instances[0].dispatch('message', { data: JSON.stringify(frame) });
    });
  }

  it('routes a typed text frame to addFeedNote with the kind from kwargs.type', async () => {
    await deliver(['text', ['A quiet room.'], { type: 'look' }]);

    expect(noteDispatches()).toEqual([
      {
        character: 'Aria',
        note: { kind: 'look', content: 'A quiet room.', timestamp: '2026-09-14T22:00:00.000Z' },
      },
    ]);
  });

  it('keeps the subject a look names', async () => {
    await deliver(['text', ['A tall woman.'], { type: 'look', subject: 'Aurelia' }]);

    expect(noteDispatches()[0]).toMatchObject({ note: { subject: 'Aurelia' } });
  });

  it('files a narrative emit as ambience, no longer as a separate ambient notice', async () => {
    await deliver(['text', ['Rain begins.'], { type: 'narrative' }]);

    expect(noteDispatches()[0]).toMatchObject({
      note: { kind: 'ambience', content: 'Rain begins.' },
    });
    expect(dispatchedTypes()).not.toContain('game/addAmbientNotice');
  });

  it('files an untyped text frame as a system note', async () => {
    await deliver(['text', ['You are now logged in.'], {}]);

    expect(noteDispatches()[0]).toMatchObject({ note: { kind: 'system' } });
  });

  it('does not make a note out of a non-text legacy frame', async () => {
    // vn_message, not logged_in (#3933): logged_in is now a dropped
    // milestone tag with no message of its own - see the control-frames
    // describe block below.
    await deliver(['vn_message', [], { text: 'A voice speaks.' }]);

    expect(noteDispatches()).toEqual([]);
    expect(dispatchedTypes()).toContain('game/addSessionMessage');
  });
});

describe('useGameSocket staff console (#3857)', () => {
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

  it('sendConsole flags the text frame so the server tags its answer', async () => {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    // The mock never opens on its own; `send` refuses a socket that is not OPEN.
    const socket = MockWebSocket.instances[0];
    socket.readyState = 1;
    vi.stubGlobal('WebSocket', Object.assign(MockWebSocket, { OPEN: 1 }));
    act(() => {
      result.current.sendConsole('Aria', '@dig East');
    });
    const frames = MockWebSocket.instances[0].sent.map((raw) => JSON.parse(raw));
    expect(frames).toContainEqual(['text', ['@dig East'], { console: true }]);
    // The line is echoed into the console above whatever the server says back.
    expect(mockDispatch).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'game/addConsoleLine',
        payload: { character: 'Aria', content: '@dig East', sent: true },
      })
    );
  });

  it('a text frame tagged console becomes a console line, never a note', async () => {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    act(() => {
      MockWebSocket.instances[0].dispatch('message', {
        data: JSON.stringify([
          'text',
          ['Created room East(#412).'],
          { console: true, type: 'error' },
        ]),
      });
    });
    const types = mockDispatch.mock.calls.map(([action]) => (action as { type: string }).type);
    expect(types).toContain('game/addConsoleLine');
    expect(types).not.toContain('game/addFeedNote');
  });
});

describe('useGameSocket puppet handshake (#3933)', () => {
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

  function dispatchedTypes(): string[] {
    return mockDispatch.mock.calls.map(([action]) => (action as { type: string }).type);
  }

  function confirmDispatches(): unknown[] {
    return mockDispatch.mock.calls
      .map(([action]) => action as { type?: string; payload?: unknown })
      .filter((action) => action.type === 'game/setSessionPuppetConfirmed')
      .map((action) => action.payload);
  }

  it('sends a puppet frame on open, never @ic', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Aria';
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.dispatch('open');
    });

    const frames = socket.sent.map((raw) => JSON.parse(raw) as unknown[]);
    expect(frames).toContainEqual(['puppet', [], { character }]);
    const textFrames = frames.filter((frame) => frame[0] === 'text');
    const hasIcCommand = textFrames.some((frame) => {
      const args = frame[1] as unknown[];
      return typeof args[0] === 'string' && args[0].startsWith('@ic');
    });
    expect(hasIcCommand).toBe(false);
  });

  it('a puppet_changed naming this socket character confirms the puppet', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Aria';
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.dispatch('open');
    });

    act(() => {
      socket.dispatch('message', {
        data: JSON.stringify([
          'puppet_changed',
          [],
          { session_id: 1, character_id: 42, character_name: character },
        ]),
      });
    });

    expect(confirmDispatches()).toEqual([{ character }]);
  });

  it('a puppet_changed for another character does not', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Aria';
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.dispatch('open');
    });

    act(() => {
      socket.dispatch('message', {
        data: JSON.stringify([
          'puppet_changed',
          [],
          { session_id: 2, character_id: 7, character_name: 'SomeoneElse' },
        ]),
      });
    });

    expect(confirmDispatches()).toEqual([]);
    expect(dispatchedTypes()).not.toContain('game/setSessionPuppetConfirmed');
  });

  it('a close clears the confirmation', async () => {
    const { result } = renderHook(() => useGameSocket());
    const character = 'Aria';
    await act(async () => {
      await result.current.connect(character);
    });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.dispatch('open');
    });
    act(() => {
      socket.dispatch('message', {
        data: JSON.stringify([
          'puppet_changed',
          [],
          { session_id: 1, character_id: 42, character_name: character },
        ]),
      });
    });
    expect(confirmDispatches()).toEqual([{ character }]);

    // A close dispatches setSessionConnectionStatus(status: false); the
    // reducer clears puppetConfirmed on that transition (gameSlice.ts).
    act(() => {
      socket.dispatch('close', { code: 1000 });
    });

    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'game/setSessionConnectionStatus',
      payload: { character, status: false },
    });
  });
});

describe('useGameSocket drops tagged compatibility text (#3933)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-19T12:00:00.000Z'));
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

  function noteDispatches(): unknown[] {
    return mockDispatch.mock.calls
      .map(([action]) => action as { type?: string; payload?: unknown })
      .filter((action) => action.type === 'game/addFeedNote')
      .map((action) => action.payload);
  }

  function dispatchedTypes(): string[] {
    return mockDispatch.mock.calls.map(([action]) => (action as { type: string }).type);
  }

  async function deliver(frame: unknown): Promise<void> {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    act(() => {
      MockWebSocket.instances[0].dispatch('message', { data: JSON.stringify(frame) });
    });
  }

  it('an interaction_echo frame adds no note', async () => {
    await deliver(['text', ['Aria waves.'], { type: 'pose', interaction_echo: true }]);

    expect(noteDispatches()).toEqual([]);
  });

  it('a lifecycle frame adds no note and no message', async () => {
    await deliver(['text', ['You become Aria.'], { type: 'lifecycle', event: 'become' }]);

    expect(noteDispatches()).toEqual([]);
    expect(dispatchedTypes()).not.toContain('game/addSessionMessage');
  });

  it('an on_entry look adds no note', async () => {
    await deliver(['text', ['Limbo...'], { type: 'look', on_entry: true }]);

    expect(noteDispatches()).toEqual([]);
  });

  it('an ordinary look still becomes a note', async () => {
    await deliver(['text', ['A quiet room.'], { type: 'look' }]);

    expect(noteDispatches()).toEqual([
      {
        character: 'Aria',
        note: { kind: 'look', content: 'A quiet room.', timestamp: '2026-09-19T12:00:00.000Z' },
      },
    ]);
  });
});

describe('useGameSocket control frames (#3933)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    __resetGameSocketModuleStateForTests();
    __resetUnknownFramesForTests();
    sessionStorage.clear();
    mockFetchPoseSubmission.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function dispatchedTypes(): string[] {
    return mockDispatch.mock.calls.map(([action]) => (action as { type: string }).type);
  }

  async function deliver(frame: unknown): Promise<void> {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    act(() => {
      MockWebSocket.instances[0].dispatch('message', { data: JSON.stringify(frame) });
    });
  }

  it('logged_in adds no message', async () => {
    await deliver(['logged_in', [], {}]);

    expect(dispatchedTypes()).not.toContain('game/addSessionMessage');
  });

  it('character_died toasts the condolence', async () => {
    await deliver(['character_died', [], { character: 'Aria', body: 'Aria has died.' }]);

    expect(mockToast).toHaveBeenCalledWith('Aria has died.');
  });

  it('webclient_options, oob and estate_settlement_opened add nothing and no diagnostic', async () => {
    await deliver(['webclient_options', [], {}]);
    await deliver(['oob', [], {}]);
    await deliver(['estate_settlement_opened', [], {}]);

    expect(dispatchedTypes()).not.toContain('game/addSessionDiagnostic');
    expect(recordedUnknownFrames()).toEqual([]);
  });

  it('an Evennia protocol frame such as channel adds nothing and no diagnostic', async () => {
    await deliver(['channel', ['General', 'hello'], {}]);

    expect(dispatchedTypes()).not.toContain('game/addSessionDiagnostic');
    expect(recordedUnknownFrames()).toEqual([]);
  });

  it('an unknown type adds no diagnostic and is recorded', async () => {
    await deliver(['mystery', [], {}]);

    expect(dispatchedTypes()).not.toContain('game/addSessionDiagnostic');
    expect(recordedUnknownFrames()).toEqual([expect.objectContaining({ type: 'mystery' })]);
  });

  it('unparseable data still adds the diagnostic', async () => {
    const { result } = renderHook(() => useGameSocket());
    await act(async () => {
      await result.current.connect('Aria');
    });
    act(() => {
      MockWebSocket.instances[0].dispatch('message', { data: '{not json' });
    });

    expect(dispatchedTypes()).toContain('game/addSessionDiagnostic');
  });
});
