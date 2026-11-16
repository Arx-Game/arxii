import { useState, type ReactNode } from 'react';
import { Stage } from '../types';
import { ChapterRailContext } from './chapterRail';
import { stageEyebrow } from './ContentsRail';

interface ChapterLeafProps {
  stage: Stage;
  title: string;
  /** Admin-editable intro copy; rendered as one paragraph, absent when empty (render-or-vanish). */
  intro?: string;
  aside?: ReactNode;
  /**
   * The right-hand rail is left empty for a panel the stage builds deep inside itself
   * and sends there with `useChapterRail` (the life page's CG points ledger). The rail
   * then holds no marginalia.
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
  const [rail, setRail] = useState<HTMLElement | null>(null);
  return (
    <div
      className={['chapter', railSlot ? 'chapter-railed' : '', className ?? ''].join(' ').trim()}
    >
      <div className="chapter-main">
        <span className="chapter-no">{stageEyebrow(stage)}</span>
        <h1>{title}</h1>
        {intro && (
          <div className="leaf-body">
            <p>{intro}</p>
          </div>
        )}
        <ChapterRailContext.Provider value={railSlot ? rail : null}>
          {children}
        </ChapterRailContext.Provider>
      </div>
      {railSlot ? (
        <div className="chapter-rail" ref={setRail} />
      ) : (
        aside && <aside aria-label="Marginalia">{aside}</aside>
      )}
    </div>
  );
}
