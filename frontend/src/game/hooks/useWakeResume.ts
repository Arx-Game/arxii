import { useEffect } from 'react';

import type { MyRosterEntry } from '@/roster/types';

/** How often the heartbeat timer notes that the page is still running. */
export const WAKE_TICK_MS = 5_000;

/**
 * How long the heartbeat may go silent before the page counts as having been
 * frozen. A page that is only hidden still runs its timers, but browsers
 * throttle them to about once a minute (Chrome's intensive throttling), so a
 * gap below this is ordinary background life, not a freeze.
 */
export const FROZEN_GAP_MS = 90_000;

/**
 * Replace the active character's socket when the page wakes from a freeze
 * (#3992, #4026).
 *
 * Edge can suspend an inactive tab and leave its WebSocket looking OPEN while
 * the transport is already gone. On wake, the socket is replaced at once so
 * the player does not wait for a stale backoff timer or click the character
 * again.
 *
 * A replacement needs evidence of a freeze, because it drops a socket that
 * may be healthy. Two things are evidence: the Page Lifecycle `resume` event,
 * which the browser fires when it unfreezes a page, and a heartbeat timer
 * that went silent for longer than `FROZEN_GAP_MS`, because a frozen page (or
 * a sleeping computer) runs no timers. Time spent in another window or tab is
 * NOT evidence: the page keeps running there and its socket stays healthy.
 * The first version of this counted time since the last focus event, so every
 * return to the window after 30 seconds replaced a live socket (#4026).
 *
 * The gap is measured with `Date.now()`, not `performance.now()`, because the
 * monotonic clock can stop while the computer sleeps, which would hide
 * exactly the gap this looks for.
 */
export function useWakeResume(
  active: MyRosterEntry['name'] | null | undefined,
  hasActiveSession: boolean,
  resume: (character: MyRosterEntry['name']) => void
): void {
  useEffect(() => {
    if (!active || !hasActiveSession) return;
    let lastTick = Date.now();
    // One wake can fire both `resume` and a visibility or focus event; the
    // first one replaces the socket and the rest must not replace the
    // replacement.
    let lastResumeAt = Number.NEGATIVE_INFINITY;

    const resumeOnce = (now: number) => {
      if (now - lastResumeAt < WAKE_TICK_MS) return;
      lastResumeAt = now;
      resume(active);
    };

    const tick = () => {
      lastTick = Date.now();
    };

    // A freeze seen while the page is still hidden is kept until it is
    // visible again, so the evidence is not lost with the refreshed tick.
    let frozenSinceVisible = false;

    // Called on the events that fire when the page comes back. The tick is
    // read before it is refreshed, so the gap covers the silent period.
    const resumeIfFrozen = () => {
      const now = Date.now();
      if (now - lastTick >= FROZEN_GAP_MS) frozenSinceVisible = true;
      lastTick = now;
      if (document.visibilityState === 'hidden' || !frozenSinceVisible) return;
      frozenSinceVisible = false;
      resumeOnce(now);
    };

    const resumeAfterFreeze = () => {
      const now = Date.now();
      lastTick = now;
      frozenSinceVisible = false;
      resumeOnce(now);
    };

    const timer = setInterval(tick, WAKE_TICK_MS);
    document.addEventListener('visibilitychange', resumeIfFrozen);
    window.addEventListener('focus', resumeIfFrozen);
    document.addEventListener('resume', resumeAfterFreeze);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', resumeIfFrozen);
      window.removeEventListener('focus', resumeIfFrozen);
      document.removeEventListener('resume', resumeAfterFreeze);
    };
  }, [active, hasActiveSession, resume]);
}
