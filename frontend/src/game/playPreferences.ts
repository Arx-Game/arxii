import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';

export type SidebarSide = 'left' | 'right';
export type PlayDensity = 'compact' | 'comfortable';
export type ReaderMode = 'threads' | 'chronological';

export interface PlayPreferences {
  proseSize: number;
  proseFamily: 'sans' | 'serif';
  measure: number;
  sidebarWidth: number;
  sidebarSide: SidebarSide;
  density: PlayDensity;
  readerMode: ReaderMode;
}

export const DEFAULT_PLAY_PREFERENCES: PlayPreferences = {
  proseSize: 14,
  proseFamily: 'sans',
  measure: 90,
  sidebarWidth: 280,
  sidebarSide: 'right',
  density: 'compact',
  readerMode: 'threads',
};

const STORAGE_KEY = 'arx:play-preferences:v2';
const LEGACY_STORAGE_KEY = 'arx:play-preferences:v1';

function clamp(value: unknown, minimum: number, maximum: number, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

export function playPreferencesKey(accountId?: number | null): string {
  return accountId == null ? STORAGE_KEY : `${STORAGE_KEY}:account:${accountId}`;
}

export function loadPlayPreferences(accountId?: number | null): PlayPreferences {
  try {
    const stored =
      window.localStorage.getItem(playPreferencesKey(accountId)) ??
      window.localStorage.getItem(LEGACY_STORAGE_KEY);
    const value = stored ? (JSON.parse(stored) as Partial<PlayPreferences>) : null;
    if (!value) return DEFAULT_PLAY_PREFERENCES;
    const normalized: PlayPreferences = {
      proseSize: clamp(value.proseSize, 12, 20, DEFAULT_PLAY_PREFERENCES.proseSize),
      proseFamily: value.proseFamily === 'serif' ? 'serif' : 'sans',
      measure: clamp(value.measure, 72, 110, DEFAULT_PLAY_PREFERENCES.measure),
      sidebarWidth: clamp(value.sidebarWidth, 240, 360, DEFAULT_PLAY_PREFERENCES.sidebarWidth),
      sidebarSide: value.sidebarSide === 'left' ? 'left' : 'right',
      density: value.density === 'comfortable' ? 'comfortable' : 'compact',
      readerMode: value.readerMode === 'chronological' ? 'chronological' : 'threads',
    };
    if (accountId != null && !window.localStorage.getItem(playPreferencesKey(accountId))) {
      window.localStorage.setItem(playPreferencesKey(accountId), JSON.stringify(normalized));
    }
    return normalized;
  } catch {
    return DEFAULT_PLAY_PREFERENCES;
  }
}

export function savePlayPreferences(
  preferences: PlayPreferences,
  accountId?: number | null
): boolean {
  try {
    window.localStorage.setItem(playPreferencesKey(accountId), JSON.stringify(preferences));
    return true;
  } catch {
    // Storage can be disabled; callers continue with in-memory preferences.
    return false;
  }
}

// Shared external store (#3759 Wave 6), keyed by storage key -- storage keys
// already encode `accountId` (`playPreferencesKey`, #3758), so this preserves
// #3758's per-account isolation while still fixing Wave 6's original bug:
// DisplaySettings.tsx and ThreadedNarrativeReader.tsx each call
// usePlayPreferences() independently, and a plain per-instance useState meant
// one instance calling `update` never re-rendered the OTHER's already-mounted
// instance for the SAME account -- so a font-size change made in
// DisplaySettings while the reader was open would leave the reader's own
// `preferences.proseSize` stale forever, and its anchor-restore effect (which
// needs to re-fire on exactly that change, per spec Acceptance A08) would
// never see it. `notifyStore` broadcasts a fresh snapshot to every instance
// subscribed to the SAME key. GameLayout.tsx's own sidebarWidth/sidebarSide
// sync is a separate, pre-existing mechanism (the `arx-play-preferences`
// window event, dispatched by DisplaySettings.tsx's own effect on every
// preferences change) -- untouched here.
const cachedPreferences = new Map<string, PlayPreferences>();
// The raw stored string each cache entry was built from -- lets
// getStoreSnapshot cheaply detect "storage changed out from under the
// cache" (e.g. a test's `localStorage.clear()`, or any other direct write
// that doesn't go through `update`, such as GameLayout.tsx's own
// sidebarWidth writes) and rebuild instead of serving a stale object
// indefinitely, without needing a 'storage' event (which doesn't fire for
// same-tab writes anyway).
const cachedRaw = new Map<string, string | null | undefined>();
const storeListeners = new Map<string, Set<() => void>>();

function getStoreSnapshot(key: string, accountId?: number | null): PlayPreferences {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    raw = null;
  }
  if (!cachedPreferences.has(key) || raw !== cachedRaw.get(key)) {
    cachedRaw.set(key, raw);
    cachedPreferences.set(key, loadPlayPreferences(accountId));
  }
  return cachedPreferences.get(key) as PlayPreferences;
}

function notifyStore(key: string, next: PlayPreferences): void {
  cachedPreferences.set(key, next);
  cachedRaw.set(key, JSON.stringify(next));
  for (const listener of storeListeners.get(key) ?? []) listener();
}

function subscribeStore(key: string, listener: () => void): () => void {
  let listeners = storeListeners.get(key);
  if (!listeners) {
    listeners = new Set();
    storeListeners.set(key, listeners);
  }
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePlayPreferences(accountId?: number | null) {
  const key = useMemo(() => playPreferencesKey(accountId), [accountId]);
  const subscribe = useCallback((listener: () => void) => subscribeStore(key, listener), [key]);
  const getSnapshot = useCallback(() => getStoreSnapshot(key, accountId), [key, accountId]);
  const preferences = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const [storageWarning, setStorageWarning] = useState(false);
  // Catches writers OTHER than this hook's own `update` (GameLayout.tsx's
  // direct sidebarWidth/sidebarSide writes via savePlayPreferences) failing
  // to persist -- #3758's original contract, preserved.
  useEffect(() => {
    const warn = () => setStorageWarning(true);
    window.addEventListener('arx-play-storage-warning', warn);
    return () => window.removeEventListener('arx-play-storage-warning', warn);
  }, []);
  const update = useCallback(
    (patch: Partial<PlayPreferences>) => {
      // Merge the patch over a FRESH read from storage, never over a stale
      // in-memory snapshot -- two independent components (DisplaySettings.tsx,
      // ThreadedNarrativeReader.tsx) each call usePlayPreferences() and each
      // held their own snapshot from their own last render; merging over that
      // meant whichever wrote second clobbered the first's change with its
      // own stale copy of every other field. Reading storage fresh here
      // layers this write on top of whatever is actually persisted right
      // now, including another instance's write.
      const next = { ...loadPlayPreferences(accountId), ...patch };
      if (!savePlayPreferences(next, accountId)) setStorageWarning(true);
      notifyStore(key, next);
    },
    [key, accountId]
  );
  return { preferences, update, storageWarning };
}

/** A single reading-position anchor: which pose, which thread, and where. */
export interface ReadingAnchor {
  poseId: string;
  threadId: string | null;
  offsetPx: number;
}

/**
 * Per-conversation storage row (#3759 Wave 6 + review finding I5).
 *
 * Threads and Chronological "share content and read state ... but keep their
 * own anchor" (ratified Decision #2) -- `anchors.threads`/`anchors.chronological`
 * are two independent slots, never a single shared `anchor` field. Switching
 * reader mode must never inherit (and then clobber, on the next save) the
 * OTHER mode's own remembered position.
 *
 * `expanded` stays a single shared field: thread expand/collapse state is NOT
 * mode-specific (Chronological has no threads UI of its own to expand).
 *
 * `expanded` (was `collapsed` through most of Wave 9; renamed in fix round 1
 * finding I-4) lists thread keys the user has EXPLICITLY expanded -- opt-IN,
 * not opt-OUT. A key `groups` doesn't yet know about (e.g. an older thread a
 * `fetchNextPage` reveals later, or -- for a row written by a pre-I-4 client
 * -- literally any key, since the field didn't exist yet) is absent from
 * this list and therefore collapsed by default, which is the correct
 * behavior; an opt-OUT `collapsed` list got this backwards for any key it
 * didn't already know about. A pre-I-4 stored row simply has no `expanded`
 * field at all, which `ThreadedNarrativeReader.tsx`'s own read path treats
 * as `[]` (nothing expanded) -- a one-time, graceful degrade for a returning
 * user on this one commit, not a migration.
 */
export interface ConversationAnchorState {
  anchors: {
    threads: ReadingAnchor | null;
    chronological: ReadingAnchor | null;
  };
  expanded: string[];
}

const ANCHOR_STORAGE_KEY = 'arx:play-anchors:v1';
const MAX_STORED_CONVERSATIONS = 100;

interface AnchorStore {
  order: string[]; // oldest first, for LRU eviction
  entries: Record<string, ConversationAnchorState>;
}

function loadAnchorStore(): AnchorStore {
  try {
    const raw = window.localStorage.getItem(ANCHOR_STORAGE_KEY);
    if (!raw) return { order: [], entries: {} };
    const parsed = JSON.parse(raw) as AnchorStore;
    if (!Array.isArray(parsed.order) || !parsed.entries || typeof parsed.entries !== 'object') {
      return { order: [], entries: {} };
    }
    return parsed;
  } catch {
    return { order: [], entries: {} };
  }
}

function saveAnchorStore(store: AnchorStore): void {
  try {
    window.localStorage.setItem(ANCHOR_STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* tab-only fallback */
  }
}

export function loadConversationAnchor(conversationKey: string): ConversationAnchorState | null {
  return loadAnchorStore().entries[conversationKey] ?? null;
}

export function saveConversationAnchor(
  conversationKey: string,
  state: ConversationAnchorState
): void {
  const store = loadAnchorStore();
  store.order = store.order.filter((key) => key !== conversationKey);
  store.order.push(conversationKey);
  store.entries[conversationKey] = state;
  while (store.order.length > MAX_STORED_CONVERSATIONS) {
    const oldest = store.order.shift();
    if (oldest !== undefined) delete store.entries[oldest];
  }
  saveAnchorStore(store);
}
