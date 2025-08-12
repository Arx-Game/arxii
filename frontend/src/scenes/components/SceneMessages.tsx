import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { fetchSceneMessages, postReaction, SceneMessage } from '../queries';

interface Props {
  sceneId: string;
}

export function SceneMessages({ sceneId }: Props) {
  const queryClient = useQueryClient();
  const messageIdRef = useRef<number>(0);
  const messagesQuery = useInfiniteQuery<{
    results: SceneMessage[];
    next?: string;
    nextCursor?: string;
  }>({
    queryKey: ['scene-messages', sceneId],
    queryFn: ({ pageParam }) => fetchSceneMessages(sceneId, pageParam),
    getNextPageParam: (lastPage) => lastPage.nextCursor || lastPage.next,
  });

  const reactionMutation = useMutation({
    mutationFn: (emoji: string) => postReaction(messageIdRef.current, emoji),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] }),
  });

  return (
    <div>
      {messagesQuery.data?.pages
        .flatMap((page) => page.results)
        .map((msg: SceneMessage) => (
          <div key={msg.id} className="border-b py-2">
            <div className="flex items-center gap-2">
              {msg.persona.thumbnail_url && (
                <img src={msg.persona.thumbnail_url} alt={msg.persona.name} className="h-6 w-6" />
              )}
              <span className="font-medium">{msg.persona.name}</span>
              <span className="text-xs text-muted-foreground">
                {new Date(msg.timestamp).toLocaleString()}
              </span>
            </div>
            <p>{msg.content}</p>
            <div className="flex gap-2">
              {msg.reactions.map((r) => (
                <button
                  key={r.emoji}
                  className="text-sm"
                  onClick={() => {
                    messageIdRef.current = msg.id;
                    reactionMutation.mutate(r.emoji);
                  }}
                >
                  {r.emoji} {r.count}
                </button>
              ))}
              <button
                className="text-sm"
                onClick={() => {
                  messageIdRef.current = msg.id;
                  reactionMutation.mutate('👍');
                }}
              >
                👍
              </button>
            </div>
          </div>
        ))}
      {messagesQuery.hasNextPage && (
        <button onClick={() => messagesQuery.fetchNextPage()} className="mt-4">
          Load More
        </button>
      )}
    </div>
  );
}
