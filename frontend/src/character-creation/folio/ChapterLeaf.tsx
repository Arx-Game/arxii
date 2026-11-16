import { useState, type ReactNode } from 'react';
import { Stage } from '../types';
import { ChapterRailContext, useRailFits } from './chapterRail';
import { stageEyebrow } from './ContentsRail';

interface ChapterLeafProps {
  stage: Stage;
  title: string;
  /** Admin-editable intro copy; rendered as one paragraph, absent when empty (render-or-vanish). */
  intro?: string;
  aside?: ReactNode;
  /**
   * The leaf is grids and takes the whole room, and from 74rem of window the right-hand
   * rail is kept for a panel the stage builds deep inside itself and sends there with
   * `useChapterRail` (the life page's CG points ledger). The leaf holds no marginalia.
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
  // The rail stands beside the whole stage only where the window has room for it; under
  // that the stage's panel stays where the stage wrote it, as it was before #5144.
  const fits = useRailFits();
  const railed = Boolean(railSlot) && fits;
  const kind = [railSlot ? 'chapter-grids' : '', railed ? 'chapter-railed' : ''];
  return (
    <div className={['chapter', ...kind, className ?? ''].filter(Boolean).join(' ')}>
      <div className="chapter-main">
        <span className="chapter-no">{stageEyebrow(stage)}</span>
        <h1>{title}</h1>
        {intro && (
          <div className="leaf-body">
            <p>{intro}</p>
          </div>
        )}
        <ChapterRailContext.Provider value={railed ? rail : null}>
          {children}
        </ChapterRailContext.Provider>
      </div>
      {railed && <div className="chapter-rail" ref={setRail} />}
      {!railSlot && aside && <aside aria-label="Marginalia">{aside}</aside>}
    </div>
  );
}
