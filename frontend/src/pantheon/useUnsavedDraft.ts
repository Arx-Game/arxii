/**
 * Keeps an editor's unsaved changes safe in this browser (a closed tab lost a staff
 * member's half-written god four times).
 *
 * The Deity Editor holds every field in the tab's memory and sends the whole page when
 * Save is pressed. This hook copies the working draft to `localStorage` while it differs
 * from what the server has, puts it back when the page is opened again, and warns before
 * the tab is closed with changes that were never saved. Nothing goes live from here: the
 * stored copy is only ever applied to the form, and Save still publishes.
 *
 * A stored draft is restored on its own only when the server's page is unchanged since the
 * draft was started. When the server's page has moved on (another editor saved), restoring
 * would silently overwrite their work on the next Save, so the stored copy is left alone
 * and the user is offered it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

const KEY_PREFIX = 'arxii:unsaved-draft:';

interface StoredDraft<T> {
  /** The server's draft (as JSON) at the time this copy was started. */
  base: string;
  draft: T;
}

function readStored<T>(storageKey: string): StoredDraft<T> | null {
  try {
    const raw = window.localStorage.getItem(KEY_PREFIX + storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredDraft<T>;
    return typeof parsed?.base === 'string' && parsed.draft ? parsed : null;
  } catch {
    return null;
  }
}

function writeStored<T>(storageKey: string, value: StoredDraft<T>): void {
  try {
    window.localStorage.setItem(KEY_PREFIX + storageKey, JSON.stringify(value));
  } catch {
    // Storage is blocked or full: the form still works, it just is not kept.
  }
}

function removeStored(storageKey: string): void {
  try {
    window.localStorage.removeItem(KEY_PREFIX + storageKey);
  } catch {
    // Nothing stored that could be removed.
  }
}

interface Options<T> {
  /** One key per thing being edited, e.g. `pantheon-being:12` or `pantheon-being:new`. */
  storageKey: string;
  /** The draft the server has; `null` until it has loaded. Must be a stable reference. */
  baseline: T | null;
  /** The form's current draft. */
  current: T;
  /** Puts a stored draft (or, to discard one, the baseline) back into the form. */
  onRestore: (draft: T) => void;
}

interface UnsavedDraft {
  /** True while the form holds changes that were never saved. */
  isDirty: boolean;
  /** Forgets the stored copy: call it once a Save has succeeded. */
  clear: () => void;
}

export function useUnsavedDraft<T>({
  storageKey,
  baseline,
  current,
  onRestore,
}: Options<T>): UnsavedDraft {
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const restoredFor = useRef<string | null>(null);
  const offerPending = useRef(false);
  const onRestoreRef = useRef(onRestore);
  onRestoreRef.current = onRestore;

  const baselineJson = baseline === null ? null : JSON.stringify(baseline);
  const isReady = readyFor === storageKey;
  const isDirty = isReady && baselineJson !== null && JSON.stringify(current) !== baselineJson;

  // Restore once per thing edited, as soon as the server's draft is known.
  useEffect(() => {
    if (baseline === null || baselineJson === null || restoredFor.current === storageKey) return;
    restoredFor.current = storageKey;
    offerPending.current = false;
    const stored = readStored<T>(storageKey);
    if (stored && JSON.stringify(stored.draft) !== baselineJson) {
      if (stored.base === baselineJson) {
        onRestoreRef.current(stored.draft);
        toast('Restored your unsaved changes.', {
          action: {
            label: 'Discard them',
            onClick: () => {
              onRestoreRef.current(baseline);
              removeStored(storageKey);
            },
          },
        });
      } else {
        offerPending.current = true;
        toast('Unsaved changes from an earlier visit. The page was saved since.', {
          duration: Infinity,
          action: {
            label: 'Restore mine',
            onClick: () => {
              offerPending.current = false;
              onRestoreRef.current(stored.draft);
            },
          },
        });
      }
    }
    setReadyFor(storageKey);
  }, [storageKey, baseline, baselineJson]);

  // Keep the stored copy equal to the working draft while it differs from the server's.
  useEffect(() => {
    if (!isReady || baselineJson === null) return;
    if (JSON.stringify(current) !== baselineJson) {
      offerPending.current = false;
      writeStored<T>(storageKey, { base: baselineJson, draft: current });
    } else if (!offerPending.current) {
      removeStored(storageKey);
    }
  }, [isReady, storageKey, baselineJson, current]);

  // Warn before a tab is closed or reloaded with changes that were never saved.
  useEffect(() => {
    if (!isDirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isDirty]);

  const clear = useCallback(() => {
    offerPending.current = false;
    removeStored(storageKey);
  }, [storageKey]);

  return { isDirty, clear };
}
