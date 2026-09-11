import { useCallback, useSyncExternalStore } from 'react';

export interface PlayPreferences {
  proseSize: number;
  proseFamily: 'sans' | 'serif';
  measure: number;
  sidebarSide: 'left' | 'right';
  readerMode: 'threads' | 'chronological';
  density: 'compact' | 'comfortable';
}
export const DEFAULT_PLAY_PREFERENCES: PlayPreferences = {
  proseSize: 14,
  proseFamily: 'sans',
  measure: 90,
  sidebarSide: 'right',
  readerMode: 'threads',
  density: 'compact',
};
const STORAGE_KEY = 'arx:play-preferences:v1';

export function loadPlayPreferences(): PlayPreferences {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? 'null'
    ) as Partial<PlayPreferences> | null;
    if (!value) return DEFAULT_PLAY_PREFERENCES;
    return {
      proseSize: Math.min(20, Math.max(12, Number(value.proseSize) || 14)),
      proseFamily: value.proseFamily === 'serif' ? 'serif' : 'sans',
      measure: Math.min(110, Math.max(72, Number(value.measure) || 90)),
      sidebarSide: value.sidebarSide === 'left' ? 'left' : 'right',
      readerMode: value.readerMode === 'chronological' ? 'chronological' : 'threads',
      density: value.density === 'comfortable' ? 'comfortable' : 'compact',
    };
  } catch {
    return DEFAULT_PLAY_PREFERENCES;
  }
}

export function savePlayPreferences(preferences: PlayPreferences): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    /* tab-only fallback */
  }
}

// Shared external store (#3759 Wave 6): DisplaySettings.tsx and
// ThreadedNarrativeReader.tsx each call usePlayPreferences() independently.
// A plain per-instance useState (the original implementation) means one
// instance calling `update` never re-renders the OTHER's already-mounted
// instance — so a font-size change made in DisplaySettings while the reader
// is open would leave the reader's own `preferences.proseSize` stale
// forever, and its anchor-restore effect (which needs to re-fire on exactly
// that change, per spec Acceptance A08) would never see it. `notifyStore`
// broadcasts a fresh snapshot to every subscribed instance on every update,
// including instances that didn't make the change themselves.
let cachedPreferences: PlayPreferences | null = null;
// The raw stored string the cache above was built from -- lets
// getStoreSnapshot cheaply detect "storage changed out from under the
// cache" (e.g. a test's `localStorage.clear()`, or any other direct write
// that doesn't go through `update`) and rebuild instead of serving a stale
// object indefinitely, without needing a 'storage' event (which doesn't
// fire for same-tab writes anyway).
let cachedRaw: string | null | undefined;
const storeListeners = new Set<() => void>();

function getStoreSnapshot(): PlayPreferences {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    raw = null;
  }
  if (cachedPreferences === null || raw !== cachedRaw) {
    cachedRaw = raw;
    cachedPreferences = loadPlayPreferences();
  }
  return cachedPreferences;
}

function notifyStore(next: PlayPreferences): void {
  cachedPreferences = next;
  cachedRaw = JSON.stringify(next);
  for (const listener of storeListeners) listener();
}

function subscribeStore(listener: () => void): () => void {
  storeListeners.add(listener);
  return () => storeListeners.delete(listener);
}

export function usePlayPreferences() {
  const preferences = useSyncExternalStore(subscribeStore, getStoreSnapshot, getStoreSnapshot);
  const update = useCallback((patch: Partial<PlayPreferences>) => {
    // Merge the patch over a FRESH read from storage, never over `current`
    // (this hook instance's own stale in-memory snapshot). Two independent
    // components (DisplaySettings.tsx, ThreadedNarrativeReader.tsx) each call
    // usePlayPreferences() and hold their own useState snapshot from their
    // own mount time; merging over `current` meant whichever wrote second
    // clobbered the first's change with its own stale copy of every other
    // field. Reading storage fresh here layers this write on top of whatever
    // is actually persisted right now, including another instance's write.
    const next = { ...loadPlayPreferences(), ...patch };
    savePlayPreferences(next);
    notifyStore(next);
  }, []);
  return { preferences, update };
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
 * `collapsed` stays a single shared field: thread collapse state is NOT
 * mode-specific (Chronological has no threads UI of its own to collapse).
 */
export interface ConversationAnchorState {
  anchors: {
    threads: ReadingAnchor | null;
    chronological: ReadingAnchor | null;
  };
  collapsed: string[];
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
