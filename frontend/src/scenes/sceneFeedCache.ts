import type { InfiniteData, QueryClient } from '@tanstack/react-query';
import { fetchInteraction } from '@/scenes/queries';
import type { Interaction } from '@/scenes/types';

type FeedPage = { results: Interaction[]; next?: string };

/**
 * The scene feed's cache keys (#4508). The scene id is the second element so
 * that a scene-wide invalidation, `sceneFeedSceneKey(sceneId)`, prefix-matches
 * every viewer's copy of that scene's feed.
 */
export function sceneFeedAllKey() {
  return ['scene-interactions'] as const;
}

export function sceneFeedSceneKey(sceneId: string | number) {
  return ['scene-interactions', String(sceneId)] as const;
}

export function sceneFeedQueryKey(args: {
  sceneId: string | number;
  accountId: number | null;
  viewerKey: string | null | undefined;
}) {
  return [
    ...sceneFeedSceneKey(args.sceneId),
    args.accountId ?? 'anonymous',
    args.viewerKey ?? 'all',
    // Cursor pages are scoped to the authorized snapshot/filter identity.
    'retained',
  ] as const;
}

/**
 * Re-fetch one pose through the per-viewer retrieve and write it into every
 * cached feed of its scene. The feed is paginated newest-first
 * (`InteractionCursorPagination` orders `-timestamp`), so a row the cache does
 * not hold yet goes at the front of the first page. A failed fetch (403, 404,
 * network) changes nothing: the viewer simply keeps the row they have.
 */
export async function refreshSceneFeedRow(
  queryClient: QueryClient,
  args: { interactionId: number; sceneId: number }
): Promise<void> {
  let row: Interaction;
  try {
    row = await fetchInteraction(args.interactionId);
  } catch {
    return;
  }
  queryClient.setQueriesData<InfiniteData<FeedPage>>(
    { queryKey: sceneFeedSceneKey(args.sceneId) },
    (data) => {
      if (!data?.pages.length) return data;
      let found = false;
      const pages = data.pages.map((page) => ({
        ...page,
        results: page.results.map((item) => {
          if (item.id !== row.id) return item;
          found = true;
          return row;
        }),
      }));
      if (!found) pages[0] = { ...pages[0], results: [row, ...pages[0].results] };
      return { ...data, pages };
    }
  );
}
