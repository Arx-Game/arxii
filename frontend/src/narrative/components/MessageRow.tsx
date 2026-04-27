/**
 * A single narrative message row in the Messages section.
 * Shows category badge, sender, excerpt, timestamp, and acknowledge button.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useAcknowledgeDelivery } from '../queries';
import { CategoryBadge } from './CategoryBadge';
import type { NarrativeMessageDelivery } from '../types';

interface MessageRowProps {
  delivery: NarrativeMessageDelivery;
}

const BODY_EXCERPT_LENGTH = 120;

export function MessageRow({ delivery }: MessageRowProps) {
  const [expanded, setExpanded] = useState(false);
  const { message, acknowledged_at } = delivery;
  const isUnread = acknowledged_at === null;

  const { mutate: acknowledge, isPending } = useAcknowledgeDelivery();

  const body = message.body;
  const excerpt =
    body.length > BODY_EXCERPT_LENGTH ? body.slice(0, BODY_EXCERPT_LENGTH) + '…' : body;
  const displayBody = expanded || body.length <= BODY_EXCERPT_LENGTH ? body : excerpt;
  const canExpand = body.length > BODY_EXCERPT_LENGTH;

  return (
    <div
      className={cn(
        'rounded-md border p-3 transition-colors',
        isUnread ? 'border-l-4 border-l-red-500 bg-muted/50' : 'border-border bg-background'
      )}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <CategoryBadge category={message.category} />
        <span className="text-sm text-muted-foreground">
          {message.sender_account !== null ? `Account #${message.sender_account}` : 'System'}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          {formatRelativeTime(message.sent_at)}
        </span>
        {isUnread && <span className="h-2 w-2 rounded-full bg-red-500" aria-label="Unread" />}
      </div>

      <button
        className="w-full cursor-pointer text-left"
        onClick={() => canExpand && setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        disabled={!canExpand}
      >
        <p className="whitespace-pre-wrap text-sm">{displayBody}</p>
        {canExpand && (
          <span className="mt-1 text-xs text-muted-foreground underline">
            {expanded ? 'Show less' : 'Show more'}
          </span>
        )}
      </button>

      <div className="mt-2 flex items-center gap-2">
        {message.related_story !== null && (
          <span
            className="cursor-not-allowed text-xs text-muted-foreground underline"
            title="Story view available in next update"
          >
            View story
          </span>
        )}
        {isUnread && (
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            disabled={isPending}
            onClick={() => acknowledge(delivery.id)}
          >
            {isPending ? 'Acknowledging…' : 'Acknowledge'}
          </Button>
        )}
      </div>
    </div>
  );
}

export function MessageRowSkeleton() {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex items-center gap-2">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-4 w-24" />
        <Skeleton className="ml-auto h-3 w-16" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="mt-1 h-4 w-3/4" />
    </div>
  );
}
