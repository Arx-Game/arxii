import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef } from 'react';
import { fetchInteractions, postInteractionReaction } from '../queries';
import type { Interaction } from '../types';
import { ActionResult } from './ActionResult';
import { FormattedContent } from '@/components/FormattedContent';
import { PersonaContextMenu } from './PersonaContextMenu';
import { useAppSelector } from '@/store/hooks';
import type { InteractionWsPayload } from '@/hooks/types';

interface Props {
  sceneId: string;
}

/** Convert a WebSocket interaction payload to the full Interaction shape for display. */
function wsPayloadToInteraction(payload: InteractionWsPayload): Interaction {
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
    target_persona_names: [],
  };
}

/** Format content based on interaction mode. */
function formatContent(content: string, mode: string) {
  switch (mode) {
    case 'say':
      return (
        <p>
          &ldquo;
          <FormattedContent content={content} />
          &rdquo;
        </p>
      );
    case 'whisper':
      return (
        <p className="italic text-muted-foreground">
          <FormattedContent content={content} />
        </p>
      );
    case 'action':
      return (
        <div className="mt-1">
          <ActionResult content={content} />
        </div>
      );
    default:
      return (
        <p>
          <FormattedContent content={content} />
        </p>
      );
  }
}

export function SceneMessages({ sceneId }: Props) {
  const queryClient = useQueryClient();
  const interactionIdRef = useRef<number>(0);

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

  const reactionMutation = useMutation({
    mutationFn: (emoji: string) => postInteractionReaction(interactionIdRef.current, emoji),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  // Merge REST historical interactions with WebSocket live interactions, deduplicated by ID
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

  return (
    <div>
      {allInteractions.map((msg) => (
        <div key={msg.id} className="border-b py-2">
          <div className="flex items-center gap-2">
            {msg.persona.thumbnail_url && (
              <img src={msg.persona.thumbnail_url} alt={msg.persona.name} className="h-6 w-6" />
            )}
            <PersonaContextMenu
              personaId={msg.persona.id}
              personaName={msg.persona.name}
              sceneId={sceneId}
            >
              {msg.persona.name}
            </PersonaContextMenu>
            <span className="text-xs text-muted-foreground">
              {new Date(msg.timestamp).toLocaleString()}
            </span>
          </div>

          {formatContent(msg.content, msg.mode)}

          <div className="flex gap-2">
            {msg.reactions.map((r) => (
              <button
                key={r.emoji}
                className="text-sm"
                onClick={() => {
                  interactionIdRef.current = msg.id;
                  reactionMutation.mutate(r.emoji);
                }}
              >
                {r.emoji} {r.count}
              </button>
            ))}
            <button
              className="text-sm"
              onClick={() => {
                interactionIdRef.current = msg.id;
                reactionMutation.mutate('\u{1F44D}');
              }}
            >
              {'\u{1F44D}'}
            </button>
          </div>
        </div>
      ))}
      {interactionsQuery.hasNextPage && (
        <button onClick={() => interactionsQuery.fetchNextPage()} className="mt-4">
          Load More
        </button>
      )}
    </div>
  );
}
