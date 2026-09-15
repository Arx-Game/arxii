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
 * Mints an id distinguishing this tab from any other. It only needs to be
 * unique within one browser session and is never sent to the server. Web
 * Crypto is the source (`randomUUID`, else `getRandomValues`, both older than
 * any browser the client supports); the clock is the last resort for a
 * runtime with no `crypto` at all, never `Math.random` (SonarCloud S2245).
 */
function mintTabId(): string {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    if (typeof crypto.getRandomValues === 'function') {
      const words = crypto.getRandomValues(new Uint32Array(2));
      return `tab-${words[0].toString(36)}${words[1].toString(36)}`;
    }
  }
  return `tab-${Date.now().toString(36)}`;
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
