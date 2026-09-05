/**
 * Per-tab browsing identity (#3479): which `RosterEntry` THIS browser tab is
 * browsing as, independent of any other tab open on the same account.
 *
 * `sessionStorage` is per-tab by the browser's own contract (a new tab or
 * window starts with none; a reload of the same tab keeps it) -- unlike
 * `localStorage`, which is shared across every tab for the origin. That
 * per-tab scoping is the whole fix for the cross-tab stomp bug (#3479 ledger
 * summary): Tab A puppeting character X must not have its `active` pointer
 * silently rewritten just because Tab B (or the Hall) changed the account's
 * durable default selection and Tab A's next `['account']` refetch mirrored
 * it in.
 *
 * Storage idiom copied from `game/threadTabsStorage.ts`: every read and
 * write sits in try/catch, and a failure (private browsing, quota, storage
 * disabled) degrades to "no stored identity" rather than throwing -- the
 * caller must render correctly with nothing stored.
 */

export const TAB_IDENTITY_KEY = 'arx.tabIdentity';

export interface TabIdentity {
  entryId: number;
  tabId: string;
}

/**
 * Mints a random id distinguishing this tab from any other. Only needs to be
 * unique within one browser session, never persisted or sent to the server,
 * so `Math.random` is an acceptable fallback where `crypto.randomUUID` is
 * unavailable (older browsers, some test runners).
 */
function mintTabId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function readTabIdentity(): TabIdentity | null {
  try {
    const raw = sessionStorage.getItem(TAB_IDENTITY_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const candidate = parsed as Partial<TabIdentity>;
    if (typeof candidate.entryId !== 'number' || typeof candidate.tabId !== 'string') {
      return null;
    }
    return { entryId: candidate.entryId, tabId: candidate.tabId };
  } catch {
    return null; // sessionStorage unavailable or unparsable -- best-effort feature.
  }
}

/**
 * Writes this tab's browsing entry id, minting a `tabId` once and keeping it
 * stable across every later write from the same tab.
 */
export function writeTabIdentity(entryId: number): void {
  try {
    const existing = readTabIdentity();
    const tabId = existing?.tabId ?? mintTabId();
    sessionStorage.setItem(TAB_IDENTITY_KEY, JSON.stringify({ entryId, tabId }));
  } catch {
    // sessionStorage unavailable -- persistence is best-effort.
  }
}

export function clearTabIdentity(): void {
  try {
    sessionStorage.removeItem(TAB_IDENTITY_KEY);
  } catch {
    // sessionStorage unavailable -- nothing to clear.
  }
}
