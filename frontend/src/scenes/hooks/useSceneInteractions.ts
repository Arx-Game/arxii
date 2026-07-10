import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { createSelector } from '@reduxjs/toolkit';
import { fetchInteractions } from '../queries';
import type { Interaction } from '../types';
import { useAppSelector } from '@/store/hooks';
import type { InteractionWsPayload } from '@/hooks/types';
import type { RootState } from '@/store/store';

/** Convert a WebSocket interaction payload to the full Interaction shape for display. */
export function wsPayloadToInteraction(payload: InteractionWsPayload): Interaction {
  return {
    id: payload.id,
    persona: payload.persona,
    content: payload.content,
    mode: payload.mode,
    visibility: 'default',
    timestamp: payload.timestamp,
    scene: payload.scene_id,
    reactions: [],
    is_favorited: false,
    place: payload.place_id,
    place_name: payload.place_name,
    receiver_persona_ids: payload.receiver_persona_ids ?? [],
    target_persona_ids: payload.target_persona_ids ?? [],
    // Endorsement fields are not present in WS payloads; initialise as empty.
    pose_kind: 'standard',
    endorsee_sheet_id: null,
    endorsable_resonances: [],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
  };
}

/**
 * Backfills a scene's interactions via REST (paginated, cursor-based) and
 * merges in any newer ones that have arrived over the WebSocket while the
 * page was open. `sceneId` is optional so composition roots like `GamePage`
 * (#2156) — which may render with no active scene — can call this hook
 * unconditionally (satisfying the rules of hooks) without triggering a
 * REST fetch or matching the WS selector against every session.
 */
export function useSceneInteractions(sceneId: string | undefined) {
  const activeCharacter = useAppSelector((state) => state.game.active);

  // Memoized selector: only recomputes when the sceneInteractions array reference changes,
  // not on every Redux state change (Fix #2)
  const selectSceneInteractions = useMemo(
    () =>
      createSelector(
        (state: RootState) => state.game.sessions[activeCharacter ?? '']?.sceneInteractions,
        (interactions) =>
          sceneId === undefined
            ? []
            : (interactions ?? []).filter(
                (ws) => ws.scene_id !== null && ws.scene_id.toString() === sceneId
              )
      ),
    [activeCharacter, sceneId]
  );
  const wsInteractions = useAppSelector(selectSceneInteractions);

  const interactionsQuery = useInfiniteQuery<{
    results: Interaction[];
    next?: string;
  }>({
    queryKey: ['scene-interactions', sceneId ?? 'none'],
    queryFn: ({ pageParam }) =>
      fetchInteractions(sceneId as string, pageParam as string | undefined),
    getNextPageParam: (lastPage) => {
      if (!lastPage.next) return undefined;
      try {
        const url = new URL(lastPage.next);
        return url.searchParams.get('cursor') ?? undefined;
      } catch {
        return undefined;
      }
    },
    initialPageParam: undefined as string | undefined,
    enabled: sceneId !== undefined,
  });

  const allInteractions = useMemo(() => {
    const restInteractions =
      interactionsQuery.data?.pages.flatMap(
        (page) => (page as { results: Interaction[] }).results
      ) ?? [];

    const restIds = new Set(restInteractions.map((i) => i.id));
    const newFromWs = wsInteractions
      .filter((ws) => !restIds.has(ws.id))
      .map(wsPayloadToInteraction);

    // REST data is sorted by cursor pagination; WS data arrives chronologically (always newer).
    // No sort needed — just append WS interactions after REST. (Fix #3)
    return [...restInteractions, ...newFromWs];
  }, [interactionsQuery.data?.pages, wsInteractions]);

  return {
    allInteractions,
    hasNextPage: interactionsQuery.hasNextPage,
    fetchNextPage: interactionsQuery.fetchNextPage,
  };
}
