import { useCallback, useEffect, useRef, useState } from 'react';
import { markPosesRead } from '../playQueries';

const DWELL_MS = 1000;
const FLUSH_INTERVAL_MS = 2000;
const MAX_BATCH = 20;

interface PoseRef {
  id: number;
  timestamp: string;
}

/**
 * Dwell-tracked read state (#3759 Task 14). Marks a pose read once it has
 * been visible (intersecting, document focused) for `DWELL_MS`, batching
 * `POST /api/play/read/` calls (Task 2) — flushed every `FLUSH_INTERVAL_MS`
 * or once `MAX_BATCH` poses have queued, whichever comes first. `markPosesRead`
 * caps a single request at 100 poses server-side (`PlayReadView`), so
 * `MAX_BATCH` stays well under that.
 *
 * Feeds `is_unread` on the next fetch of any play endpoint, and (since #3774)
 * the per-character counts `account_attention()` computes for the top bar's
 * badges. Before #3774 this comment claimed the badges picked it up with no
 * further wiring; they did not, which is what #3774 fixed.
 *
 * The focus gate is re-evaluated on `visibilitychange`/`focus` as well as on
 * intersection changes: the `IntersectionObserver` callback only fires on a
 * threshold *crossing*, so an element already on-screen when the tab was
 * backgrounded (or the whole page loaded backgrounded) produces no crossing
 * when focus returns and would otherwise never start its dwell timer.
 */
export function usePoseReadTracking() {
  const pending = useRef<Map<HTMLElement, PoseRef>>(new Map());
  const dwellTimers = useRef<Map<HTMLElement, ReturnType<typeof setTimeout>>>(new Map());
  // Elements the IntersectionObserver currently reports as intersecting,
  // tracked independently of `document.hasFocus()`. The observer only fires
  // on a threshold *crossing* — an element that was already on-screen when
  // the tab was backgrounded (or the whole page loaded backgrounded) never
  // produces a new crossing when focus returns, so without this durable
  // record it would never start a dwell timer until the user happened to
  // scroll it fully out and back in. The visibilitychange/focus handler
  // below re-derives dwell eligibility from this set instead.
  const intersecting = useRef<Set<HTMLElement>>(new Set());
  const queued = useRef<PoseRef[]>([]);
  const flushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(() => {
    if (queued.current.length === 0) return;
    const batch = queued.current.splice(0, MAX_BATCH);
    // Fire-and-forget: `markPosesRead` throws on any non-ok response, and
    // nothing else awaits this call, so an uncaught rejection here becomes an
    // unhandled promise rejection on every network blip, session expiry, or
    // transient 5xx — the exact fan-out shape #3743 burned a month's Sentry
    // quota on (one broken path, thousands of events). Swallow and log
    // instead of propagating. This is read-state bookkeeping the reader
    // doesn't need to react to, so no retry: `batch` is already spliced out
    // of `queued.current`, and if the pose scrolls back into view later it
    // simply gets marked again.
    markPosesRead(batch).catch((error: unknown) => {
      console.error('Failed to mark poses read', error);
    });
    // More than MAX_BATCH could still be queued (dwell timers can fire faster
    // than the flush interval drains them); if so, reschedule immediately
    // instead of waiting for the next dwell event to call scheduleFlush()
    // again, which could stall the remainder indefinitely.
    if (queued.current.length > 0) scheduleFlushRef.current();
  }, []);

  // `flush` and `scheduleFlush` are mutually recursive (flush reschedules
  // itself; scheduleFlush's timer calls flush), so a plain closure over
  // `scheduleFlush` from inside `flush` would need `scheduleFlush` declared
  // first, and `scheduleFlush` depends on `flush`, which depends on
  // `scheduleFlush`... A ref sidesteps the cycle without adding either
  // callback to the other's dependency array.
  const scheduleFlushRef = useRef<() => void>(() => {});

  const scheduleFlush = useCallback(() => {
    if (flushTimer.current) return;
    flushTimer.current = setTimeout(() => {
      flushTimer.current = null;
      flush();
    }, FLUSH_INTERVAL_MS);
  }, [flush]);
  // Keep the ref current every render so flush()'s reference to it (above)
  // always calls the latest scheduleFlush, not a stale closure.
  scheduleFlushRef.current = scheduleFlush;

  // Shared by the observer callback (a fresh intersection) and the
  // focus/visibility handler (an element already intersecting when focus
  // returns) so the timer-creation logic exists in exactly one place.
  // Guards against double-starting a timer for an element that already has
  // one running.
  const startDwellTimer = useCallback(
    (el: HTMLElement, pose: PoseRef) => {
      if (dwellTimers.current.has(el)) return;
      dwellTimers.current.set(
        el,
        setTimeout(() => {
          queued.current.push(pose);
          dwellTimers.current.delete(el);
          if (queued.current.length >= MAX_BATCH) flush();
          else scheduleFlush();
        }, DWELL_MS)
      );
    },
    [flush, scheduleFlush]
  );

  const handleIntersect = useCallback<IntersectionObserverCallback>(
    (entries) => {
      for (const entry of entries) {
        const el = entry.target as HTMLElement;
        const pose = pending.current.get(el);
        if (!pose) continue;
        if (entry.isIntersecting) {
          intersecting.current.add(el);
          if (document.hasFocus()) startDwellTimer(el, pose);
        } else {
          intersecting.current.delete(el);
          const timer = dwellTimers.current.get(el);
          if (timer) {
            clearTimeout(timer);
            dwellTimers.current.delete(el);
          }
        }
      }
    },
    [startDwellTimer]
  );

  // Fires on tab-switch-away/back and minimize/restore (`visibilitychange`)
  // and on app-switching on desktop, where the tab stays visible but the
  // window itself loses OS focus (`focus`/`blur` on `window`). Either event
  // re-evaluates every element the observer currently reports as
  // intersecting — as if its intersection had just started — so a
  // screenful of poses that were already on-screen when the reader
  // regained focus still starts its dwell timer instead of waiting for an
  // unrelated future scroll to produce a new intersection crossing.
  const handleFocusRegained = useCallback(() => {
    if (!document.hasFocus()) return;
    for (const el of intersecting.current) {
      const pose = pending.current.get(el);
      if (!pose) continue;
      startDwellTimer(el, pose);
    }
  }, [startDwellTimer]);

  useEffect(() => {
    document.addEventListener('visibilitychange', handleFocusRegained);
    window.addEventListener('focus', handleFocusRegained);
    return () => {
      document.removeEventListener('visibilitychange', handleFocusRegained);
      window.removeEventListener('focus', handleFocusRegained);
    };
  }, [handleFocusRegained]);

  // Built once, synchronously, during the first render — deliberately NOT
  // inside a `useEffect`. `observe()` below is invoked by a rendered pose's
  // OWN effect (see `PoseReadTarget` in ThreadedNarrativeReader.tsx), and
  // React fires a descendant's passive effects before its ancestor's; if
  // this observer were built in this hook's own `useEffect`, every pose
  // already mounted on first paint would call `observe()` while the
  // observer was still null, silently never subscribing the poses visible
  // when the reader first opens — exactly the case dwell-tracking exists to
  // catch. A lazy `useState` initializer runs during render (before any
  // effect, descendant or ancestor), so it's always ready before the first
  // `observe()` call. React may invoke this initializer twice under
  // StrictMode (dev only); the discarded instance is never `.observe()`'d,
  // so that's inert.
  const [observer] = useState(() => new IntersectionObserver(handleIntersect));

  useEffect(
    () => () => {
      // Send whatever is still queued (up to FLUSH_INTERVAL_MS worth of
      // pending read-marks) before tearing down — otherwise navigating away
      // from a scene silently drops them, since nothing else ever flushes on
      // unmount.
      flush();
      observer.disconnect();
    },
    [observer, flush]
  );

  const observe = useCallback(
    (element: HTMLElement, pose: PoseRef) => {
      pending.current.set(element, pose);
      observer.observe(element);
      return () => {
        pending.current.delete(element);
        intersecting.current.delete(element);
        const timer = dwellTimers.current.get(element);
        if (timer) clearTimeout(timer);
        dwellTimers.current.delete(element);
        observer.unobserve(element);
      };
    },
    [observer]
  );

  return { observe };
}
