/**
 * Client-local persistence for the conversation-tab layout (#2165, spec
 * decision 5a): thread KEYS only — never message content. Keyed per
 * account+character+scene; a character keeps at most one scene's entry per account.
 */
const STORAGE_PREFIX = 'arx:threadTabs:v2:account:';

export interface StoredThreadTabs {
  openThreadTabs: string[];
  activeThreadTab: string | null;
}

function storageKey(character: string, sceneId: string, accountId?: number | null): string {
  return `${STORAGE_PREFIX}${accountId == null ? 'anonymous' : accountId}:${character}:${sceneId}`;
}

export function loadThreadTabs(
  character: string,
  sceneId: string,
  accountId?: number | null
): StoredThreadTabs | null {
  try {
    const raw = localStorage.getItem(storageKey(character, sceneId, accountId));
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
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('arx-play-storage-warning'));
    return null; // localStorage unavailable or unparsable — best-effort feature.
  }
}

export function saveThreadTabs(
  character: string,
  sceneId: string,
  value: StoredThreadTabs,
  accountId?: number | null
): void {
  try {
    const keep = storageKey(character, sceneId, accountId);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (
        key &&
        key.startsWith(
          `${STORAGE_PREFIX}${accountId == null ? 'anonymous' : accountId}:${character}:`
        ) &&
        key !== keep
      ) {
        localStorage.removeItem(key);
      }
    }
    localStorage.setItem(keep, JSON.stringify(value));
  } catch {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('arx-play-storage-warning'));
    // localStorage unavailable — persistence is best-effort.
  }
}
