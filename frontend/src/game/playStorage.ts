/** Account-scoped browser storage used by the live play surface. */

const ACCOUNT_PREFIXES = [
  'arx:play-preferences:v2:account:',
  'arx:play-anchors:v2:account:',
  'arx:threadTabs:v2:account:',
  'arx:play-draft:v2:',
];

/**
 * Removes account-owned drafts and reader state.
 *
 * A logout has no trusted account id after the mutation completes, so it
 * removes every account-scoped play key. An account switch can pass the old
 * id to remove only that account's state. Unscoped legacy keys are never read
 * or migrated.
 */
export function clearAccountPlayStorage(accountId?: number | null): void {
  let keys: string[];
  try {
    keys = Object.keys(localStorage);
  } catch {
    // Storage is optional; the in-memory client remains usable.
    keys = [];
  }
  let sessionKeys: string[];
  try {
    sessionKeys = Object.keys(sessionStorage);
  } catch {
    sessionKeys = [];
  }
  const accountToken = accountId == null ? null : String(accountId);
  const shouldClear = (key: string): boolean => {
    if (key.startsWith('arx:play-draft:v2:')) {
      return accountToken == null || key.startsWith(`arx:play-draft:v2:${accountToken}:`);
    }
    if (accountToken == null) return ACCOUNT_PREFIXES.some((prefix) => key.startsWith(prefix));
    return (
      key === `arx:play-preferences:v2:account:${accountToken}` ||
      key === `arx:play-anchors:v2:account:${accountToken}` ||
      key.startsWith(`arx:threadTabs:v2:account:${accountToken}:`)
    );
  };
  for (const key of keys) {
    if (!shouldClear(key)) continue;
    try {
      localStorage.removeItem(key);
    } catch {
      // Quota/private mode failures are reported by the owning feature.
    }
  }
  for (const key of sessionKeys) {
    if (!shouldClear(key)) continue;
    try {
      sessionStorage.removeItem(key);
    } catch {
      // See localStorage handling above.
    }
  }
}
