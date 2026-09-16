/**
 * VisionCard (#3779) — one vision on the sheet, in the treatment reserved for visions.
 * Names the being only when the sender revealed it (or the viewer is staff, which the
 * server decides). A clue or an episode attachment reads as a footnote, never a control.
 */

import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';
import type { Vision } from '../types';
import { VISION_FRAME_CLASS, VISION_GLYPH, VISION_TEXT_CLASS } from '../visionStyle';

interface VisionCardProps {
  vision: Vision;
}

export function VisionCard({ vision }: VisionCardProps) {
  return (
    <article className={cn(VISION_FRAME_CLASS, 'px-3 py-2')} data-testid="vision-card">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden="true" className="text-emerald-600 dark:text-emerald-400">
          {VISION_GLYPH}
        </span>
        <span className="uppercase tracking-wide">Vision</span>
        {vision.being_name && <span>from {vision.being_name}</span>}
        <span className="ml-auto">{formatRelativeTime(vision.sent_at)}</span>
      </div>
      <p className={cn('whitespace-pre-wrap', VISION_TEXT_CLASS)}>{vision.body}</p>
      {(vision.clue_slug || vision.episode_title) && (
        <p className="mt-1 text-xs text-muted-foreground">
          {vision.clue_slug && <span>A clue came with it: {vision.clue_slug}. </span>}
          {vision.episode_title && <span>Of the episode {vision.episode_title}.</span>}
        </p>
      )}
    </article>
  );
}
