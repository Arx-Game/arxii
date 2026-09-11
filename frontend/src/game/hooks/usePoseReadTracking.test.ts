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

  it('flushes any still-pending queue on unmount instead of losing it', () => {
    // Before this fix, nothing ever flushed on unmount — up to
    // FLUSH_INTERVAL_MS (2s) worth of dwell-completed poses were silently
    // dropped when the reader unmounted (e.g. navigating away from a scene)
    // before the periodic flush timer got a chance to fire.
    const { result, unmount } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 99, timestamp: '2026-01-01T00:00:00Z' });

    act(() => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
      vi.advanceTimersByTime(1000); // dwell completes; queued but not yet flushed
    });
    expect(playQueries.markPosesRead).not.toHaveBeenCalled();

    unmount();

    expect(playQueries.markPosesRead).toHaveBeenCalledWith([
      { id: 99, timestamp: '2026-01-01T00:00:00Z' },
    ]);
  });

  it('drains a backlog larger than one batch to completion without a new dwell event', () => {
    // A burst larger than MAX_BATCH (20) must not strand its remainder
    // waiting indefinitely for some unrelated future pose to dwell-complete
    // and re-trigger scheduling; every queued item eventually reaches
    // markPosesRead from this one burst alone.
    const { result } = renderHook(() => usePoseReadTracking());
    const elements = Array.from({ length: 45 }, () => document.createElement('div'));
    elements.forEach((el, i) =>
      result.current.observe(el, { id: i, timestamp: `2026-01-01T00:00:00Z` })
    );

    act(() => {
      observerInstance.trigger(elements.map((el) => ({ target: el, isIntersecting: true })));
      vi.advanceTimersByTime(1000);
      // Advance well past FLUSH_INTERVAL_MS with no new intersection/dwell
      // event at all — only this initial burst's own scheduling is allowed
      // to account for every item.
      vi.advanceTimersByTime(5000);
    });

    const totalMarked = vi
      .mocked(playQueries.markPosesRead)
      .mock.calls.reduce((sum, [batch]) => sum + batch.length, 0);
    expect(totalMarked).toBe(45);
  });

  it('does not dwell-track an already-intersecting pose while backgrounded, then starts on focus return', () => {
    // Regression for the bug where a screenful of poses already intersecting
    // when the tab was backgrounded (or the page loaded backgrounded) never
    // got a fresh IntersectionObserver crossing when focus returned, so they
    // never started their dwell timer at all.
    vi.mocked(document.hasFocus).mockReturnValue(false);

    const { result } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 55, timestamp: '2026-01-01T00:00:00Z' });

    act(() => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
    });
    act(() => {
      // Well past both DWELL_MS and FLUSH_INTERVAL_MS — nothing should ever
      // have started a timer while backgrounded, no matter how long it sits.
      vi.advanceTimersByTime(5000);
    });
    expect(playQueries.markPosesRead).not.toHaveBeenCalled();

    // Focus returns: flip the stub the same way a real tab-switch-back would
    // flip `document.hasFocus()`, then fire the event the hook listens for.
    vi.mocked(document.hasFocus).mockReturnValue(true);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    // The dwell timer only just started on focus return — not yet elapsed.
    expect(playQueries.markPosesRead).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1000);
      vi.advanceTimersByTime(2100); // clear the batch-flush debounce too
    });
    expect(playQueries.markPosesRead).toHaveBeenCalledWith([
      { id: 55, timestamp: '2026-01-01T00:00:00Z' },
    ]);
  });

  it('does not double-start a dwell timer on focus return for a pose the observer already gated in', () => {
    // If the element was already intersecting AND focused (the ordinary
    // case), a subsequent visibilitychange/focus event must not start a
    // second, overlapping dwell timer for it (double-counting risk).
    const { result } = renderHook(() => usePoseReadTracking());
    const el = document.createElement('div');
    result.current.observe(el, { id: 8, timestamp: '2026-01-01T00:00:00Z' });

    act(() => {
      observerInstance.trigger([{ target: el, isIntersecting: true }]);
    });
    act(() => {
      // Fire focus-regained mid-dwell; a second timer here would push a
      // duplicate read-mark onto the queue when it later fires.
      vi.advanceTimersByTime(500);
      document.dispatchEvent(new Event('visibilitychange'));
      vi.advanceTimersByTime(500);
      vi.advanceTimersByTime(2100);
    });

    expect(playQueries.markPosesRead).toHaveBeenCalledTimes(1);
    expect(playQueries.markPosesRead).toHaveBeenCalledWith([
      { id: 8, timestamp: '2026-01-01T00:00:00Z' },
    ]);
  });

  it('does not leak the visibilitychange/focus listeners across unmount', () => {
    const addDocListener = vi.spyOn(document, 'addEventListener');
    const removeDocListener = vi.spyOn(document, 'removeEventListener');
    const addWinListener = vi.spyOn(window, 'addEventListener');
    const removeWinListener = vi.spyOn(window, 'removeEventListener');

    const { unmount } = renderHook(() => usePoseReadTracking());
    expect(addDocListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
    expect(addWinListener).toHaveBeenCalledWith('focus', expect.any(Function));

    unmount();

    expect(removeDocListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
    expect(removeWinListener).toHaveBeenCalledWith('focus', expect.any(Function));
  });
});
