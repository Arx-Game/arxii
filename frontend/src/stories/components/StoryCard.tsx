/**
 * StoryCard — single story row in the My Active Stories list.
 */

import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/relativeTime';
import { ScopeBadge } from './ScopeBadge';
import { StatusBadge } from './StatusBadge';
import type { MyActiveStoryEntry } from '../types';

interface StoryCardProps {
  entry: MyActiveStoryEntry;
}

export function StoryCard({ entry }: StoryCardProps) {
  const navigate = useNavigate();

  const chapterEpisodeCrumb =
    entry.chapter_order != null && entry.episode_order != null
      ? `Ch ${entry.chapter_order}, Ep ${entry.episode_order}`
      : null;

  return (
    <Card
      className="cursor-pointer transition-colors hover:bg-accent"
      role="button"
      tabIndex={0}
      onClick={() => void navigate(`/stories/${entry.story_id}`)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          void navigate(`/stories/${entry.story_id}`);
        }
      }}
    >
      <CardContent className="flex items-center justify-between gap-4 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold">{entry.story_title}</span>
            <ScopeBadge scope={entry.scope} />
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <StatusBadge status={entry.status} label={entry.status_label} />
            {chapterEpisodeCrumb && <span>{chapterEpisodeCrumb}</span>}
            {entry.scheduled_real_time && (
              <span>Scheduled {formatRelativeTime(entry.scheduled_real_time)}</span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
