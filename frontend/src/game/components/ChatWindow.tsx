import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { GameMessage } from '@/hooks/types';
import { EvenniaMessage } from './EvenniaMessage';
import { GAME_MESSAGE_TYPE } from '@/hooks/types';
import { narrativeKeys } from '@/narrative/queries';

interface ChatWindowProps {
  messages: Array<GameMessage & { id: string }>;
}

export function ChatWindow({ messages }: ChatWindowProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const queryClient = useQueryClient();

  // Invalidate narrative cache when a real-time narrative message arrives so
  // the messages section and unread counter update without waiting for a refetch.
  useEffect(() => {
    const hasNarrative = messages.some((m) => m.type === GAME_MESSAGE_TYPE.NARRATIVE);
    if (hasNarrative) {
      void queryClient.invalidateQueries({ queryKey: narrativeKeys.all });
    }
  }, [messages, queryClient]);

  useEffect(() => {
    if (autoScroll) {
      const el = containerRef.current;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [messages, autoScroll]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const isAtBottom = Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight) < 1;
    setAutoScroll(isAtBottom);
  };

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="mb-2 min-h-0 flex-1 overflow-y-auto rounded bg-black p-4 font-mono text-white"
    >
      {messages.length === 0 ? (
        <p className="text-muted-foreground">No messages yet...</p>
      ) : (
        messages.map((message) => (
          <div
            key={message.id}
            className={
              message.type === GAME_MESSAGE_TYPE.NARRATIVE
                ? 'mb-2 border-l-2 border-red-500 bg-red-950/20 px-2'
                : 'mb-2'
            }
          >
            <span className="text-xs text-muted-foreground">
              {new Date(message.timestamp).toLocaleTimeString()}
            </span>
            <EvenniaMessage
              content={message.content}
              className={
                message.type === GAME_MESSAGE_TYPE.NARRATIVE
                  ? 'text-red-300'
                  : message.type === GAME_MESSAGE_TYPE.SYSTEM
                    ? 'text-blue-400'
                    : message.type === GAME_MESSAGE_TYPE.ACTION
                      ? 'text-green-400'
                      : message.type === GAME_MESSAGE_TYPE.CHANNEL
                        ? 'text-purple-400'
                        : message.type === GAME_MESSAGE_TYPE.ERROR
                          ? 'text-red-400'
                          : 'text-white'
              }
            />
          </div>
        ))
      )}
    </div>
  );
}
