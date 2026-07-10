import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { GameMessage } from '@/hooks/types';
import { EvenniaMessage } from './EvenniaMessage';

interface SystemLaneProps {
  messages: Array<GameMessage & { id: string }>;
}

/**
 * Muted, collapsible strip for system/channel/error chatter (#2156). Chat
 * bubbles on the primary feed are the ratified presentation; this lane keeps
 * the raw Evennia-style log line output around (still useful for debugging
 * and out-of-narrative notices) without letting it read as a terminal —
 * no `bg-black`/`font-mono` on the lane itself, just a quiet compact strip
 * that expands on demand.
 */
export function SystemLane({ messages }: SystemLaneProps) {
  const [collapsed, setCollapsed] = useState(true);

  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="shrink-0 border-t px-3 py-1 text-xs text-muted-foreground">
      <button
        type="button"
        onClick={() => setCollapsed((prev) => !prev)}
        aria-expanded={!collapsed}
        className="flex w-full items-center gap-1 py-1 text-left transition-colors hover:text-foreground"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronDown className="h-3 w-3 shrink-0" />
        )}
        <span>System</span>
        {collapsed && (
          <span
            data-testid="system-lane-count"
            className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-muted px-1"
          >
            {messages.length}
          </span>
        )}
      </button>
      {!collapsed && (
        <div
          data-testid="system-lane-messages"
          className="max-h-40 space-y-0.5 overflow-y-auto pb-1 pl-4"
        >
          {messages.map((message) => (
            <div key={message.id} className="flex gap-2">
              <span className="shrink-0 text-muted-foreground/70">
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
              <EvenniaMessage content={message.content} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
