/** The public-reaction news feed (#1450) — recent deeds + scandals the active character's
 * societies are aware of, newest first. The browse/pull face of the public-reaction center; the
 * immersive push echoes and in-world hubs are later slices. */
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { usePublicFeedQuery } from '../queries';
import type { PublicFeedItem } from '../types';

function FeedRow({ item }: { item: PublicFeedItem }) {
  const isScandal = item.kind === 'scandal';
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <Badge variant={isScandal ? 'destructive' : 'default'} className="mt-0.5 shrink-0">
          {isScandal ? 'Scandal' : 'Deed'}
        </Badge>
        <div className="min-w-0">
          <p className="font-medium">{item.subject}</p>
          <p className="text-muted-foreground">{item.headline}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function NewsFeed({ viewerId }: { viewerId: number | null }) {
  const { data, isLoading, isError } = usePublicFeedQuery(viewerId);

  if (viewerId == null) {
    return (
      <p className="text-muted-foreground">Choose an active character to catch up on the news.</p>
    );
  }
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }
  if (isError) {
    return <p className="text-destructive">The news feed could not be loaded.</p>;
  }
  if (!data || data.length === 0) {
    return (
      <p className="text-muted-foreground">
        There's no news circulating in your circles right now.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {data.map((item, index) => (
        <FeedRow key={`${item.kind}-${index}`} item={item} />
      ))}
    </div>
  );
}
