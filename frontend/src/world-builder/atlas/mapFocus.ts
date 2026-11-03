/**
 * The handshake behind a page's "On the map" door (#4983): the page remembers which
 * region map to open and which title to select, the Atlas opens on that map (its own
 * last-location memory, `useAtlasState`), and the region map page selects the title
 * once and forgets it. A title with no land has nothing to click, so this is how a
 * titular or potential title is reached on the map.
 */
const FOCUS_KEY = 'world-builder-atlas:focus-title';

export function rememberMapFocus(accountId: number | string, regionId: number, titleId: number) {
  try {
    window.localStorage.setItem(
      `world-builder-atlas:${accountId}:last-location`,
      JSON.stringify({ kind: 'regionmap', id: regionId })
    );
    window.sessionStorage.setItem(FOCUS_KEY, String(titleId));
  } catch {
    // storage unavailable: the door still opens the map, unselected
  }
}

/**
 * The title a page asked the map to select. Reading and forgetting are separate
 * because React runs a state initializer twice under StrictMode: the page reads
 * in the initializer and forgets in a mount effect.
 */
export function peekMapFocus(): number | null {
  try {
    const raw = window.sessionStorage.getItem(FOCUS_KEY);
    if (raw == null) return null;
    const id = Number(raw);
    return Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
}

export function clearMapFocus() {
  try {
    window.sessionStorage.removeItem(FOCUS_KEY);
  } catch {
    // nothing to forget
  }
}
