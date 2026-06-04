/**
 * useServerDraft — reactive editor draft against a server-side record.
 *
 * Every Mission Studio editor (NodePage, OptionPage, ...) previously did
 * ``useState(() => derive(record))`` once on mount. On React Query
 * refetch (mutation invalidation, window-focus, manual invalidate) the
 * parent received a fresh ``record`` prop but the draft never
 * re-derived — clicking Save sent the user's stale draft, silently
 * overwriting any server-side changes.
 *
 * This hook fixes that:
 *
 * - Initializes draft from the server record.
 * - Tracks a baseline = the last server view the draft was synced to.
 * - When server changes AND the user has not edited, auto-pulls
 *   (draft = baseline = new derive(record)). No banner, no UI noise.
 * - When server changes AND the user has edited, leaves the draft
 *   alone but exposes ``serverChanged`` so the editor can warn
 *   "this record updated server-side; refresh to merge".
 * - ``pullFromServer()`` manually overwrites the draft with the
 *   current server view (the "refresh" action).
 *
 * Returns the same tuple-shape as ``useState`` plus the extras.
 */

import { useEffect, useRef, useState } from 'react';

export interface ServerDraftAPI<D> {
  draft: D;
  setDraft: (next: D | ((prev: D) => D)) => void;
  /** True when ``draft`` differs from the baseline (= user has edited). */
  dirty: boolean;
  /** True when the current server view differs from the baseline (= a refetch arrived). */
  serverChanged: boolean;
  /** Discard user edits, snap draft + baseline to the current server view. */
  pullFromServer: () => void;
}

export function useServerDraft<T, D>(server: T, derive: (s: T) => D): ServerDraftAPI<D> {
  const [draft, setDraft] = useState<D>(() => derive(server));
  const [baseline, setBaseline] = useState<D>(() => derive(server));
  // Track the server reference we last synced to so we don't re-derive
  // on every render (React Query produces a new wrapper object per fetch
  // even when the contents are unchanged — equality is by reference).
  const lastServerRef = useRef<T>(server);

  useEffect(() => {
    if (lastServerRef.current === server) return;
    const nextDerived = derive(server);
    const draftEqualsBaseline = JSON.stringify(draft) === JSON.stringify(baseline);
    if (draftEqualsBaseline) {
      setBaseline(nextDerived);
      setDraft(nextDerived);
    } else {
      // User has edits; leave draft alone, but update baseline so the
      // "server changed" banner can fire and the user can pullFromServer
      // if they want to discard their edits.
      setBaseline(nextDerived);
    }
    lastServerRef.current = server;
  }, [server, draft, baseline, derive]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const serverChanged =
    lastServerRef.current !== server && JSON.stringify(baseline) !== JSON.stringify(derive(server));

  const pullFromServer = () => {
    const fresh = derive(server);
    setBaseline(fresh);
    setDraft(fresh);
  };

  return { draft, setDraft, dirty, serverChanged, pullFromServer };
}
