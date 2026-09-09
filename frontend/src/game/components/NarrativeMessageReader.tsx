import { useEffect, useRef, useState } from 'react';
import type { GameMessage, GameMessageType } from '@/hooks/types';
import { EvenniaMessage } from './EvenniaMessage';

interface NarrativeMessageReaderProps {
  messages: Array<GameMessage & { id: string }>;
}

const LABELS: Partial<Record<GameMessageType, string>> = {
  system: 'World',
  text: 'World',
  chat: 'Conversation',
  action: 'Action',
  channel: 'Channel',
  narrative: 'Narrative',
  gemit: 'Narrative',
  error: 'Notice',
};

/**
 * Presents non-scene socket feedback as readable narrative cards.
 *
 * The game surface must remain useful in a quiet room, so this deliberately
 * does not expose raw command output or a terminal-shaped black transcript.
 */
export function NarrativeMessageReader({ messages }: NarrativeMessageReaderProps) {
  const readerRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    if (pinned && readerRef.current) readerRef.current.scrollTop = readerRef.current.scrollHeight;
  }, [messages, pinned]);

  return (
    <div
      ref={readerRef}
      onScroll={() => {
        const el = readerRef.current;
        if (el) setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 12);
      }}
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
      style={{
        fontSize: 'var(--play-prose-size, 14px)',
        fontFamily: 'var(--play-prose-family, ui-sans-serif)',
      }}
      aria-label="World history"
    >
      <div className="mx-auto w-full max-w-[var(--play-reading-measure,90ch)] space-y-3 px-4 py-5">
        {messages.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <h2 className="font-serif text-xl">The world is quiet.</h2>
            <p className="sr-only">No messages yet</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Look around, meet the people here, or begin a conversation below.
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className="rounded-lg border bg-card/70 px-4 py-3 shadow-sm">
              <header className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                <span className="font-medium">{LABELS[message.type] ?? 'World'}</span>
                <time dateTime={new Date(message.timestamp).toISOString()}>
                  {new Date(message.timestamp).toLocaleTimeString([], {
                    hour: 'numeric',
                    minute: '2-digit',
                  })}
                </time>
              </header>
              <EvenniaMessage content={message.content} presentation="prose" />
            </article>
          ))
        )}
      </div>
    </div>
  );
}
