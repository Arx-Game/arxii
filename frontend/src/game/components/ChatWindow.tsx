import { useEffect, useRef, useState } from 'react';
import type { GameMessage } from '../../hooks/types';
import { EvenniaMessage } from './EvenniaMessage';
import { GAME_MESSAGE_TYPE } from '../../hooks/types';

interface ChatWindowProps {
  messages: Array<GameMessage & { id: string }>;
  isConnected: boolean;
}

export function ChatWindow({ messages, isConnected }: ChatWindowProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

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
    <>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Game Window</h2>
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-sm text-muted-foreground">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="mb-4 h-96 overflow-y-auto rounded bg-black p-4 font-mono text-white"
      >
        {messages.length === 0 ? (
          <p className="text-muted-foreground">No messages yet...</p>
        ) : (
          messages.map((message) => (
            <div key={message.id} className="mb-2">
              <span className="text-xs text-muted-foreground">
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
              <EvenniaMessage
                content={message.content}
                className={
                  message.type === GAME_MESSAGE_TYPE.SYSTEM
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
    </>
  );
}
