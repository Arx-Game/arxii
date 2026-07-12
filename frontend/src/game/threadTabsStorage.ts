/**
 * Client-local persistence for the conversation-tab layout (#2165, spec
 * decision 5a): thread KEYS only — never message content. Keyed per
 * character+scene; a character keeps at most one scene's entry.
 */
const STORAGE_PREFIX = 'arx:threadTabs:';

export interface StoredThreadTabs {
  openThreadTabs: string[];
  activeThreadTab: string | null;
}

function storageKey(character: string, sceneId: string): string {
  return `${STORAGE_PREFIX}${character}:${sceneId}`;
}

export function loadThreadTabs(character: string, sceneId: string): StoredThreadTabs | null {
  try {
    const raw = localStorage.getItem(storageKey(character, sceneId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const candidate = parsed as Partial<StoredThreadTabs>;
    if (!Array.isArray(candidate.openThreadTabs)) return null;
    return {
      openThreadTabs: candidate.openThreadTabs.filter((k): k is string => typeof k === 'string'),
      activeThreadTab:
        typeof candidate.activeThreadTab === 'string' ? candidate.activeThreadTab : null,
    };
  } catch {
    return null; // localStorage unavailable or unparsable — best-effort feature.
  }
}

export function saveThreadTabs(character: string, sceneId: string, value: StoredThreadTabs): void {
  try {
    const keep = storageKey(character, sceneId);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (key && key.startsWith(`${STORAGE_PREFIX}${character}:`) && key !== keep) {
        localStorage.removeItem(key);
      }
    }
    localStorage.setItem(keep, JSON.stringify(value));
  } catch {
    // localStorage unavailable — persistence is best-effort.
  }
}
