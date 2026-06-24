/** React Query hooks for the public-reaction tidings feed (#1450). */
import { useQuery } from '@tanstack/react-query';

import { fetchPublicFeed } from './api';

export const tidingsKeys = {
  feed: (viewerId: number) => ['tidings', 'feed', viewerId] as const,
};

/** The active character's public feed (`viewerId` = a RosterEntry pk). Disabled until there's an
 * active character — public awareness scopes to the active character, never the account. */
export function usePublicFeedQuery(viewerId: number | null) {
  return useQuery({
    queryKey: tidingsKeys.feed(viewerId ?? 0),
    queryFn: () => fetchPublicFeed(viewerId as number),
    enabled: viewerId != null,
  });
}
