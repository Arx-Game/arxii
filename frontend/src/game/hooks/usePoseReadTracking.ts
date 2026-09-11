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
 * Feeds `is_unread` indirectly: once a pose is marked read here, the next
 * fetch reflects it, and `attention.ts`'s existing direct/ambient derivation
 * (unchanged by this task) starts counting it correctly with no further
 * wiring.
 */
export function usePoseReadTracking() {
  const pending = useRef<Map<HTMLElement, PoseRef>>(new Map());
  const dwellTimers = useRef<Map<HTMLElement, ReturnType<typeof setTimeout>>>(new Map());
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
  }, []);

  const scheduleFlush = useCallback(() => {
    if (flushTimer.current) return;
    flushTimer.current = setTimeout(() => {
      flushTimer.current = null;
      flush();
    }, FLUSH_INTERVAL_MS);
  }, [flush]);

  const handleIntersect = useCallback<IntersectionObserverCallback>(
    (entries) => {
      for (const entry of entries) {
        const el = entry.target as HTMLElement;
        const pose = pending.current.get(el);
        if (!pose) continue;
        if (entry.isIntersecting && document.hasFocus()) {
          if (!dwellTimers.current.has(el)) {
            dwellTimers.current.set(
              el,
              setTimeout(() => {
                queued.current.push(pose);
                dwellTimers.current.delete(el);
                if (queued.current.length >= MAX_BATCH) flush();
                else scheduleFlush();
              }, DWELL_MS)
            );
          }
        } else {
          const timer = dwellTimers.current.get(el);
          if (timer) {
            clearTimeout(timer);
            dwellTimers.current.delete(el);
          }
        }
      }
    },
    [flush, scheduleFlush]
  );

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

  useEffect(() => () => observer.disconnect(), [observer]);

  const observe = useCallback(
    (element: HTMLElement, pose: PoseRef) => {
      pending.current.set(element, pose);
      observer.observe(element);
      return () => {
        pending.current.delete(element);
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
