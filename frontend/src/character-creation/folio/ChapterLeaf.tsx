import type { ReactNode } from 'react';
import { Stage } from '../types';
import { CHAPTER_ORDINALS } from './ContentsRail';

interface ChapterLeafProps {
  stage: Stage;
  title: string;
  /** Admin-editable intro copy; rendered as one paragraph, absent when empty (render-or-vanish). */
  intro?: string;
  aside?: ReactNode;
  /** Single-column leaf with no rail (used while a stage keeps its old internals). */
  wide?: boolean;
  className?: string;
  children: ReactNode;
}

export function ChapterLeaf({
  stage,
  title,
  intro,
  aside,
  wide,
  className,
  children,
}: ChapterLeafProps) {
  return (
    <div className={['chapter', wide ? 'chapter-wide' : '', className ?? ''].join(' ').trim()}>
      <div className="chapter-main">
        <span className="chapter-no">{CHAPTER_ORDINALS[stage]}</span>
        <h1>{title}</h1>
        {intro && (
          <div className="leaf-body">
            <p>{intro}</p>
          </div>
        )}
        {children}
      </div>
      {!wide && aside && <aside aria-label="Marginalia">{aside}</aside>}
    </div>
  );
}
