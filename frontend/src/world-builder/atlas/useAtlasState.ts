/**
 * useAtlasState (#3477 Task 4) — the Atlas's client-only navigation memory:
 * which node is open, and the per-account trail of bookmarks/recents that
 * survives a reload. A "node" is one of the four view kinds the shell knows
 * how to render (`AtlasPage`'s `view.kind` switch) — Tasks 5-7 fill in the
 * 'roomgrid'/'roomdoc'/'areadoc' bodies behind that same union; this hook
 * only remembers where the viewer was, never fetches anything itself.
 *
 * All storage is keyed per-account (`accountId`) so switching accounts on a
 * shared browser never bleeds one account's trail into another's. Every
 * localStorage read/write is try/catch wrapped — private browsing, quota,
 * or disabled storage can all throw, and a failure here should degrade to
 * "nothing remembered," never a crash.
 */
import { useCallback, useEffect, useState } from 'react';

import { useAccount } from '@/store/hooks';

export type AtlasViewKind = 'area' | 'roomgrid' | 'roomdoc' | 'areadoc';

export interface AtlasView {
  kind: AtlasViewKind;
  id: number;
}

export interface AtlasHistoryEntry extends AtlasView {
  name: string;
  visitedAt: string;
}

const RECENTS_LIMIT = 8;

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable (private browsing, quota, disabled) — the atlas's
    // navigation memory is a convenience, never a requirement to function.
  }
}

function sameNode(a: AtlasView, b: AtlasView): boolean {
  return a.kind === b.kind && a.id === b.id;
}

function storageKeys(accountId: number | string) {
  const ns = `world-builder-atlas:${accountId}`;
  return {
    lastLocation: `${ns}:last-location`,
    pinned: `${ns}:pinned`,
    recents: `${ns}:recents`,
  };
}

export interface UseAtlasStateResult {
  /** The currently open node, or `null` before a location has ever been chosen/restored. */
  view: AtlasView | null;
  /** Navigate to `next`; `name` (when given) records the visit in Recent. */
  setView: (next: AtlasView, name?: string) => void;
  pinned: AtlasHistoryEntry[];
  isPinned: (node: AtlasView) => boolean;
  togglePinned: (entry: AtlasHistoryEntry) => void;
  recents: AtlasHistoryEntry[];
}

export function useAtlasState(): UseAtlasStateResult {
  const account = useAccount();
  const accountId = account?.id ?? 'anon';

  const [view, setViewState] = useState<AtlasView | null>(() =>
    readJSON<AtlasView | null>(storageKeys(accountId).lastLocation, null)
  );
  const [pinned, setPinned] = useState<AtlasHistoryEntry[]>(() =>
    readJSON<AtlasHistoryEntry[]>(storageKeys(accountId).pinned, [])
  );
  const [recents, setRecents] = useState<AtlasHistoryEntry[]>(() =>
    readJSON<AtlasHistoryEntry[]>(storageKeys(accountId).recents, [])
  );

  // Re-read when the acting account changes (e.g. an account switch without a
  // full page reload) so one account's trail never leaks into another's.
  useEffect(() => {
    const keys = storageKeys(accountId);
    setViewState(readJSON<AtlasView | null>(keys.lastLocation, null));
    setPinned(readJSON<AtlasHistoryEntry[]>(keys.pinned, []));
    setRecents(readJSON<AtlasHistoryEntry[]>(keys.recents, []));
  }, [accountId]);

  const setView = useCallback(
    (next: AtlasView, name?: string) => {
      const keys = storageKeys(accountId);
      setViewState(next);
      writeJSON(keys.lastLocation, next);
      if (name) {
        setRecents((prev) => {
          const updated = [
            { ...next, name, visitedAt: new Date().toISOString() },
            ...prev.filter((entry) => !sameNode(entry, next)),
          ].slice(0, RECENTS_LIMIT);
          writeJSON(keys.recents, updated);
          return updated;
        });
      }
    },
    [accountId]
  );

  const isPinned = useCallback(
    (node: AtlasView) => pinned.some((entry) => sameNode(entry, node)),
    [pinned]
  );

  const togglePinned = useCallback(
    (entry: AtlasHistoryEntry) => {
      const keys = storageKeys(accountId);
      setPinned((prev) => {
        const updated = prev.some((existing) => sameNode(existing, entry))
          ? prev.filter((existing) => !sameNode(existing, entry))
          : [entry, ...prev];
        writeJSON(keys.pinned, updated);
        return updated;
      });
    },
    [accountId]
  );

  return { view, setView, pinned, isPinned, togglePinned, recents };
}
