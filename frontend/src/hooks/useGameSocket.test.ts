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

import { useGameSocket } from './useGameSocket';

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
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  addEventListener(type: string, callback: Listener): void {
    (this.listeners[type] ??= []).push(callback);
  }

  send(): void {
    // Outbound frames aren't under test here.
  }

  dispatch(type: string, event: unknown = {}): void {
    (this.listeners[type] ?? []).forEach((callback) => callback(event));
  }
}

describe('useGameSocket connection generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
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
