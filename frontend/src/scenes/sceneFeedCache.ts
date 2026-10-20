import type { InfiniteData, QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/errors';
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

// One entry per pose being refetched: `dirty` means another frame arrived meanwhile.
const inFlight = new Map<number, { dirty: boolean; done: Promise<void> }>();

/**
 * Re-fetch one pose through the per-viewer retrieve and write it into every
 * cached feed of its scene. The feed is paginated newest-first
 * (`InteractionCursorPagination` orders `-timestamp`), so a row the cache does
 * not hold yet goes at the front of the first page, unless it is older than
 * everything loaded (a later page will bring it). A 403 or 404 means the viewer
 * may not see the row, so nothing changes; any other failure is thrown.
 *
 * No cached feed for the scene means nothing to update, so nothing is fetched.
 * Frames for a pose that arrive while its fetch is in flight share one follow-up
 * fetch instead of one each.
 */
export function refreshSceneFeedRow(
  queryClient: QueryClient,
  args: { interactionId: number; sceneId: number }
): Promise<void> {
  const cached = queryClient.getQueryCache().findAll({ queryKey: sceneFeedSceneKey(args.sceneId) });
  if (cached.length === 0) return Promise.resolve();
  const pending = inFlight.get(args.interactionId);
  if (pending) {
    pending.dirty = true;
    return pending.done;
  }
  const entry = { dirty: false, done: Promise.resolve() };
  inFlight.set(args.interactionId, entry);
  entry.done = (async () => {
    try {
      // A failed fetch must not drop a frame that arrived meanwhile: go again, and
      // throw the failure only when nothing newer is waiting.
      for (;;) {
        entry.dirty = false;
        try {
          await fetchIntoFeed(queryClient, args);
        } catch (error) {
          if (!entry.dirty) throw error;
        }
        if (!entry.dirty) return;
      }
    } finally {
      inFlight.delete(args.interactionId);
    }
  })();
  return entry.done;
}

async function fetchIntoFeed(
  queryClient: QueryClient,
  args: { interactionId: number; sceneId: number }
): Promise<void> {
  let row: Interaction;
  try {
    row = await fetchInteraction(args.interactionId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) return;
    throw error;
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
      if (!found && !isOlderThanLoaded(row, data)) {
        pages[0] = { ...pages[0], results: [row, ...pages[0].results] };
      }
      return { ...data, pages };
    }
  );
}

/** True when the row is no newer than the oldest loaded row: paging will bring it, so do not add it now. */
function isOlderThanLoaded(row: Interaction, data: InfiniteData<FeedPage>): boolean {
  const loaded = data.pages.flatMap((page) => page.results);
  const oldest = loaded.at(-1);
  return oldest !== undefined && Date.parse(row.timestamp) <= Date.parse(oldest.timestamp);
}
