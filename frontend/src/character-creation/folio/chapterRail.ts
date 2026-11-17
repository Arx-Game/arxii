import { createContext, useContext } from 'react';

/**
 * The place in a chapter's right-hand panel that a stage fills from deep inside itself
 * (#5148). `ChapterLeaf` provides it when it is given `railSlot`: the slot stands at the
 * foot of the panel, under the "CG selections" every stage shows, and a component portals
 * its own list there (the life page's choices). Null where there is no slot: the list
 * then renders where it is written.
 */
export const ChapterRailContext = createContext<HTMLElement | null>(null);

export function useChapterRail(): HTMLElement | null {
  return useContext(ChapterRailContext);
}
