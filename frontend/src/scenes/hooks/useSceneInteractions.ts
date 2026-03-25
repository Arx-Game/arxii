import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { fetchInteractions } from '../queries';
import type { Interaction } from '../types';
import { useAppSelector } from '@/store/hooks';
import type { InteractionWsPayload } from '@/hooks/types';

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
  };
}

export function useSceneInteractions(sceneId: string) {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const wsInteractions = useAppSelector((state) => {
    if (!activeCharacter) return [];
    return (state.game.sessions[activeCharacter]?.sceneInteractions ?? []).filter(
      (ws) => ws.scene_id !== null && ws.scene_id.toString() === sceneId
    );
  });

  const interactionsQuery = useInfiniteQuery<{
    results: Interaction[];
    next?: string;
  }>({
    queryKey: ['scene-interactions', sceneId],
    queryFn: ({ pageParam }) => fetchInteractions(sceneId, pageParam as string | undefined),
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

    return [...restInteractions, ...newFromWs].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }, [interactionsQuery.data?.pages, wsInteractions]);

  return {
    allInteractions,
    hasNextPage: interactionsQuery.hasNextPage,
    fetchNextPage: interactionsQuery.fetchNextPage,
  };
}
