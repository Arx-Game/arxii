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
});
