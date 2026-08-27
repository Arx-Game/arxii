/** The public-reaction tidings feed (#1450) — recent deeds + scandals the active character's
 * societies are aware of, newest first. The browse/pull face of the public-reaction center; the
 * immersive push echoes and in-world criers/hubs are later slices. */
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { usePublicFeedQuery } from '../queries';
import type { PublicFeedItem, FeedItemKind } from '../types';

// PLACEHOLDER wording (#3412 hygiene fold-in): every PublicFeedItemKindEnum value gets a
// distinct, neutral fallback label when the server doesn't send a `category` override —
// previously only deed/scandal were distinguished and the other 7 kinds (pardon, crisis,
// proclamation, birthday, stature, menace, verdict) all rendered as "Scandal". These are
// deliberately plain enum-derived names, not lore-authoritative copy; a later design pass
// can replace them.
const KIND_LABELS: Record<FeedItemKind, string> = {
  deed: 'Deed',
  scandal: 'Scandal',
  pardon: 'Pardon',
  crisis: 'Crisis',
  proclamation: 'Proclamation',
  birthday: 'Birthday',
  stature: 'Stature',
  menace: 'Menace',
  verdict: 'Verdict',
};

// Deed reads as a positive/celebratory tone; every other kind (scandal included) reads as
// attention-worthy/negative until each gets its own tone treatment (PLACEHOLDER, #3412).
function isPositiveTone(kind: FeedItemKind): boolean {
  return kind === 'deed';
}

function FeedRow({ item }: { item: PublicFeedItem }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <Badge
          variant={isPositiveTone(item.kind) ? 'default' : 'destructive'}
          className="mt-0.5 shrink-0"
        >
          {item.category ?? KIND_LABELS[item.kind]}
        </Badge>
        <div className="min-w-0">
          <p className="font-medium">{item.subject}</p>
          <p className="text-muted-foreground">{item.headline}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function TidingsFeed({
  viewerId,
  isResolvingViewer = false,
}: {
  viewerId: number | null;
  /**
   * True while the active-character selection itself is still being resolved
   * (account hydration, or the roster query catching up to it) — #3412 review
   * fix. `viewerId == null` is ambiguous on its own: it means "no active
   * character" both during that resolving window AND once resolution genuinely
   * lands on no selection. Without this flag every mount (e.g. a hard reload
   * landing directly on /tidings, which isn't behind ProtectedRoute) flashed
   * "Choose an active character" for a fully-selected player.
   */
  isResolvingViewer?: boolean;
}) {
  const { data, isLoading, isError } = usePublicFeedQuery(viewerId);

  if (isResolvingViewer) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }
  if (viewerId == null) {
    return (
      <p className="text-muted-foreground">
        Choose an active character to catch up on the tidings.
      </p>
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
    return <p className="text-destructive">The tidings feed could not be loaded.</p>;
  }
  if (!data || data.length === 0) {
    return (
      <p className="text-muted-foreground">
        There are no tidings circulating in your circles right now.
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
