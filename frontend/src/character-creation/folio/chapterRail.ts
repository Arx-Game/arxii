import { createContext, useContext } from 'react';

/**
 * The element a stage's own panel is rendered into so that it stands as the page's
 * right-hand rail (#5144). `ChapterLeaf` provides it when it is given `railSlot`. Null
 * where the leaf keeps no such place: the panel then renders where it is written.
 */
export const ChapterRailContext = createContext<HTMLElement | null>(null);

export function useChapterRail(): HTMLElement | null {
  return useContext(ChapterRailContext);
}
