/**
 * StoryRoomsPage — `/story-rooms` (#2450 Fix 2, spec Decision 1's promised
 * player web surface). Lists the account's own story-room access grants
 * (`GET /api/gm/my-story-grants/`, `world.gm.story_views.MyStoryGrantsViewSet`)
 * with a Join/Leave button per row, dispatching the same
 * `join_story_room`/`leave_story_room` REGISTRY actions telnet already has
 * (`actions/definitions/story_builder.py`) — telnet keeps parity, this closes
 * the "web button" gap.
 *
 * Each row dispatches as `row.character_id` (the exact character the grant
 * was issued to), not any notion of "the active character" — see
 * `MyStoryGrantSerializer`'s doc comment (`world/gm/serializers.py`) for why.
 * Styled after `GMDashboardPage` (`@/stories/pages/GMDashboardPage`) — a
 * simple bordered-section list with an inline action button per row.
 */
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';

import { useMyStoryGrantsQuery, useStoryRoomAction } from '../queries';
import type { MyStoryGrant } from '../types';

export function StoryRoomsPage() {
  return (
    <ErrorBoundary>
      <StoryRoomsContent />
    </ErrorBoundary>
  );
}

function StoryRoomsContent() {
  const { data, isLoading, isError, error } = useMyStoryGrantsQuery();
  const action = useStoryRoomAction();

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-8 text-center text-destructive">
        Failed to load your story-room invitations: {error?.message}
      </div>
    );
  }

  const grants = data?.results ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Story Rooms</h1>
      <Card>
        <CardContent className="p-4">
          {grants.length === 0 ? (
            <p className="text-sm text-muted-foreground">No story invitations right now.</p>
          ) : (
            <ul className="space-y-2">
              {grants.map((grant) => (
                <StoryRoomGrantRow
                  key={grant.id}
                  grant={grant}
                  isPending={
                    action.isPending && action.variables?.characterId === grant.character_id
                  }
                  onJoin={() =>
                    action.mutate({
                      characterId: grant.character_id,
                      key: 'join_story_room',
                      kwargs: { room_id: grant.room_id },
                    })
                  }
                  onLeave={() =>
                    action.mutate({
                      characterId: grant.character_id,
                      key: 'leave_story_room',
                      kwargs: {},
                    })
                  }
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface StoryRoomGrantRowProps {
  grant: MyStoryGrant;
  isPending: boolean;
  onJoin: () => void;
  onLeave: () => void;
}

function StoryRoomGrantRow({ grant, isPending, onJoin, onLeave }: StoryRoomGrantRowProps) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
      <div className="min-w-0">
        <p className="truncate font-medium">{grant.room_name}</p>
        <p className="truncate text-xs text-muted-foreground">
          Granted to {grant.character_name} on {new Date(grant.created_at).toLocaleDateString()}
        </p>
      </div>
      {grant.is_inside ? (
        <Button size="sm" variant="outline" disabled={isPending} onClick={onLeave}>
          {isPending ? 'Leaving…' : 'Leave'}
        </Button>
      ) : (
        <Button size="sm" disabled={isPending} onClick={onJoin}>
          {isPending ? 'Joining…' : 'Join'}
        </Button>
      )}
    </li>
  );
}
