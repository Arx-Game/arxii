/**
 * TableStoryRoster — story list in the TableDetailPage Stories tab.
 *
 * GM sees ALL stories at this table.
 * Player (member or guest) sees only stories they participate in.
 * Filtering is done by passing the appropriate `gm_table` filter and
 * optionally scoping by the viewer's own participation.
 *
 * For the current phase we query `/api/stories/?gm_table=<id>` and let
 * the backend handle visibility. The backend queryset already limits
 * non-GM viewers to stories they participate in.
 */

import { useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useStoryList } from '@/stories/queries';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TableStoryRosterProps {
  table: GMTable;
  onRemove?: (storyId: number, storyTitle: string) => void;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function StoryRowSkeleton() {
  return (
    <div className="flex items-center justify-between py-2">
      <Skeleton className="h-4 w-52" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TableStoryRoster({ table, onRemove }: TableStoryRosterProps) {
  const navigate = useNavigate();
  const isGM = table.viewer_role === 'gm' || table.viewer_role === 'staff';

  // The stories API filters by primary_table; the backend further scopes
  // non-GM viewers to stories they participate in (via the get_queryset visibility rules).
  const { data, isLoading } = useStoryList({ primary_table: table.id });

  if (isLoading) {
    return (
      <div className="space-y-1">
        {[0, 1, 2].map((i) => (
          <StoryRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  const stories = data?.results ?? [];

  if (stories.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        {isGM
          ? 'No stories at this table yet.'
          : "You don't participate in any stories at this table."}
      </p>
    );
  }

  return (
    <div className="divide-y">
      {stories.map((story) => (
        <div key={story.id} className="flex items-center justify-between py-3">
          <div className="min-w-0 flex-1">
            <button
              type="button"
              className="text-left font-medium hover:underline"
              onClick={() => void navigate(`/stories/${story.id}`)}
            >
              {story.title}
            </button>
            <div className="mt-0.5 flex gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="text-xs">
                {story.scope}
              </Badge>
              <span>{story.status}</span>
            </div>
          </div>
          {isGM && onRemove && (
            <button
              type="button"
              className="ml-4 rounded border border-destructive/30 px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => onRemove(story.id, story.title)}
            >
              Remove
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
