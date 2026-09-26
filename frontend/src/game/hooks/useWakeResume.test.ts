import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FROZEN_GAP_MS, useWakeResume } from './useWakeResume';

// A page in another window or tab keeps running, so its timers keep firing:
// `vi.advanceTimersByTime` models that. A frozen page (or a sleeping computer)
// runs no timers while the wall clock moves on: `vi.setSystemTime` alone
// models that. The hook must tell the two apart (#4026).

let visibility: DocumentVisibilityState = 'visible';

function fire(target: Document | Window, type: string, state?: DocumentVisibilityState): void {
  if (state) visibility = state;
  target.dispatchEvent(new Event(type));
}

function freezeFor(ms: number): void {
  vi.setSystemTime(Date.now() + ms);
}

describe('useWakeResume', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    visibility = 'visible';
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibility,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps the socket when the player returns from another window', () => {
    const resume = vi.fn();
    renderHook(() => useWakeResume('Aria', true, resume));

    // Forty seconds in another application, then back: the original trigger
    // replaced the socket here, and the old one leaked.
    vi.advanceTimersByTime(40_000);
    fire(window, 'focus');
    // A long stay behind another window, even a hidden one, is not a freeze.
    fire(document, 'visibilitychange', 'hidden');
    vi.advanceTimersByTime(10 * 60_000);
    fire(document, 'visibilitychange', 'visible');
    fire(window, 'focus');

    expect(resume).not.toHaveBeenCalled();
  });

  it('replaces the socket once when the page wakes from a freeze', () => {
    const resume = vi.fn();
    renderHook(() => useWakeResume('Aria', true, resume));

    fire(document, 'visibilitychange', 'hidden');
    freezeFor(FROZEN_GAP_MS + 1_000);
    fire(document, 'visibilitychange', 'visible');
    fire(window, 'focus');

    expect(resume).toHaveBeenCalledTimes(1);
    expect(resume).toHaveBeenCalledWith('Aria');
  });

  it('replaces the socket once on the Page Lifecycle resume event', () => {
    const resume = vi.fn();
    renderHook(() => useWakeResume('Aria', true, resume));

    freezeFor(FROZEN_GAP_MS + 1_000);
    fire(document, 'resume');
    fire(document, 'visibilitychange', 'visible');

    expect(resume).toHaveBeenCalledTimes(1);
  });

  it('waits for the page to be visible before replacing after a freeze', () => {
    const resume = vi.fn();
    renderHook(() => useWakeResume('Aria', true, resume));

    freezeFor(FROZEN_GAP_MS + 1_000);
    fire(document, 'visibilitychange', 'hidden');
    expect(resume).not.toHaveBeenCalled();

    // The freeze is remembered while hidden, so coming back still replaces.
    vi.advanceTimersByTime(20_000);
    fire(document, 'visibilitychange', 'visible');
    expect(resume).toHaveBeenCalledTimes(1);
  });

  it('does nothing without an active session, and stops listening on unmount', () => {
    const resume = vi.fn();
    renderHook(() => useWakeResume('Aria', false, resume));
    freezeFor(FROZEN_GAP_MS + 1_000);
    fire(document, 'resume');

    const { unmount } = renderHook(() => useWakeResume('Aria', true, resume));
    unmount();
    freezeFor(FROZEN_GAP_MS + 1_000);
    fire(document, 'resume');
    fire(document, 'visibilitychange', 'visible');

    expect(resume).not.toHaveBeenCalled();
  });
});
