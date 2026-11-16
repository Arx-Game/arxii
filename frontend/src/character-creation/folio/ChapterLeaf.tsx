import { useState, type ReactNode } from 'react';
import { Stage } from '../types';
import { ChapterRailContext } from './chapterRail';
import { stageEyebrow } from './ContentsRail';

interface ChapterLeafProps {
  stage: Stage;
  title: string;
  /** Admin-editable intro copy; rendered as one paragraph, absent when empty (render-or-vanish). */
  intro?: string;
  /** The right-hand panel: the "CG selections" every stage shows, then the stage's notes. */
  aside?: ReactNode;
  /**
   * The leaf is grids and takes the whole room instead of a reading column, and the
   * panel ends with a slot the stage fills from deep inside itself with
   * `useChapterRail` (the life page's choices, under the same "CG selections" as every
   * other stage; #5148).
   */
  railSlot?: boolean;
  className?: string;
  children: ReactNode;
}

export function ChapterLeaf({
  stage,
  title,
  intro,
  aside,
  railSlot,
  className,
  children,
}: ChapterLeafProps) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const kind = railSlot ? 'chapter-grids' : '';
  return (
    <div className={['chapter', kind, className ?? ''].filter(Boolean).join(' ')}>
      <div className="chapter-main">
        <span className="chapter-no">{stageEyebrow(stage)}</span>
        <h1>{title}</h1>
        {intro && (
          <div className="leaf-body">
            <p>{intro}</p>
          </div>
        )}
        <ChapterRailContext.Provider value={slot}>{children}</ChapterRailContext.Provider>
      </div>
      {(aside || railSlot) && (
        <aside aria-label="Marginalia">
          {aside}
          {railSlot && <div className="rail-slot" ref={setSlot} />}
        </aside>
      )}
    </div>
  );
}
