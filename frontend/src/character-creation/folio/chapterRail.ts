import { createContext, useContext, useSyncExternalStore } from 'react';

/**
 * The element a stage's own panel is rendered into so that it stands as the page's
 * right-hand rail (#5144). `ChapterLeaf` provides it when it is given `railSlot` and the
 * window is wide enough for a rail beside the whole stage. Null otherwise: the panel then
 * renders where it is written.
 */
export const ChapterRailContext = createContext<HTMLElement | null>(null);

export function useChapterRail(): HTMLElement | null {
  return useContext(ChapterRailContext);
}

/** The width from which a chapter keeps its rail beside the leaf (cg.css folds it at 74rem). */
const RAIL_FITS = '(min-width: 74rem)';

function subscribe(onChange: () => void) {
  const query = window.matchMedia?.(RAIL_FITS);
  query?.addEventListener('change', onChange);
  return () => query?.removeEventListener('change', onChange);
}

/** Whether the window is wide enough for the rail. True where the browser cannot say. */
export function useRailFits(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(RAIL_FITS)?.matches ?? true);
}
