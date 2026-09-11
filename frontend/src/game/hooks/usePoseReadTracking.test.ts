import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { usePoseReadTracking } from './usePoseReadTracking';
import * as playQueries from '../playQueries';

class MockIntersectionObserver {
  callback: IntersectionObserverCallback;
  constructor(cb: IntersectionObserverCallback) {
    this.callback = cb;
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  trigger(entries: Partial<IntersectionObserverEntry>[]) {
    this.callback(entries as IntersectionObserverEntry[], this as unknown as IntersectionObserver);
  }
}

describe('usePoseReadTracking', () => {
  let observerInstance: MockIntersectionObserver;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'IntersectionObserver',
      // vitest 5's `vi.fn()` only honors a constructor call (`new
      // IntersectionObserver(cb)`, which the hook under test uses) when the
      // wrapped implementation is a `function`/`class` expression — an arrow
      // function has no [[Construct]] slot at all, so `new`-ing a
      // vi.fn()-wrapped arrow throws "is not a constructor" regardless of
      // what the hook does. Returning `observerInstance` (an object) from
      // this constructor function overrides the implicit `this`, so
      // `new IntersectionObserver(cb)` still evaluates to the same
      // `observerInstance` the test asserts against below.
      vi.fn(function (cb: IntersectionObserverCallback) {
        observerInstance = new MockIntersectionObserver(cb);
        return observerInstance;
      })
    );
    vi.spyOn(playQueries, 'markPosesRead').mockResolvedValue({ marked: 1 });
    // jsdom's document.hasFocus() always reports false (there is no real
    // window manager to grant focus) — the hook gates dwell-marking on it,
    // so without this stub NEITHER test below would ever see a dwell timer
    // fire for the right reason. Stub it true: these tests simulate a reader
    // actively looking at a foregrounded tab.
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('marks a pose read after it has been visible for 1 second', () => {
    const { result } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 42, timestamp: '2026-01-01T00:00:00Z' });

    act(() => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
    });
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(playQueries.markPosesRead).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
      vi.advanceTimersByTime(2100); // clear the batch-flush debounce too
    });
    expect(playQueries.markPosesRead).toHaveBeenCalledWith([
      { id: 42, timestamp: '2026-01-01T00:00:00Z' },
    ]);
  });

  it('does not mark read if the pose leaves view before 1 second', () => {
    const { result } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 7, timestamp: '2026-01-01T00:00:00Z' });

    act(() => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
    });
    act(() => {
      vi.advanceTimersByTime(500);
      observerInstance.trigger([{ target: el, isIntersecting: false }]);
      vi.advanceTimersByTime(3000);
    });
    expect(playQueries.markPosesRead).not.toHaveBeenCalled();
  });

  it('does not throw when markPosesRead rejects, and stays usable for the next dwell cycle', async () => {
    // #3743 burned a month's Sentry quota when one uncaught rejection fanned
    // out across every affected call — flush()'s fire-and-forget
    // markPosesRead call must swallow (and log) a rejection rather than
    // leaving it unhandled. vitest fails the test itself if a promise
    // rejects unhandled during it, so this test's mere completion (no
    // uncaught-rejection failure) is part of what it proves.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.mocked(playQueries.markPosesRead).mockRejectedValueOnce(new Error('network blip'));

    const { result } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 1, timestamp: '2026-01-01T00:00:00Z' });

    await act(async () => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
      // *Async* advance so the fake-timer clock also drains the microtask
      // queue between ticks, letting flush()'s `.catch()` actually settle.
      await vi.advanceTimersByTimeAsync(1000);
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(playQueries.markPosesRead).toHaveBeenCalledWith([
      { id: 1, timestamp: '2026-01-01T00:00:00Z' },
    ]);
    expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to mark poses read', expect.any(Error));

    // The hook itself must still work for a later pose — a rejected flush
    // must not corrupt or wedge the queue/timer state for the next cycle.
    const el2 = document.createElement('div');
    result.current.observe(el2, { id: 2, timestamp: '2026-01-01T00:01:00Z' });
    await act(async () => {
      observerInstance.trigger([{ target: el2, isIntersecting: true }]);
      await vi.advanceTimersByTimeAsync(1000);
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(playQueries.markPosesRead).toHaveBeenLastCalledWith([
      { id: 2, timestamp: '2026-01-01T00:01:00Z' },
    ]);

    consoleErrorSpy.mockRestore();
  });
});
