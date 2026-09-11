import { useCallback, useState } from 'react';

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

export function usePlayPreferences() {
  const [preferences, setPreferences] = useState(loadPlayPreferences);
  const update = useCallback((patch: Partial<PlayPreferences>) => {
    // Merge the patch over a FRESH read from storage, never over `current`
    // (this hook instance's own stale in-memory snapshot). Two independent
    // components (DisplaySettings.tsx, ThreadedNarrativeReader.tsx) each call
    // usePlayPreferences() and hold their own useState snapshot from their
    // own mount time; merging over `current` meant whichever wrote second
    // clobbered the first's change with its own stale copy of every other
    // field. Reading storage fresh here layers this write on top of whatever
    // is actually persisted right now, including another instance's write.
    setPreferences(() => {
      const next = { ...loadPlayPreferences(), ...patch };
      savePlayPreferences(next);
      return next;
    });
  }, []);
  return { preferences, update };
}

export interface ConversationAnchorState {
  anchor: { poseId: string; threadId: string | null; offsetPx: number } | null;
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
