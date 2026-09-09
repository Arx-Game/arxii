import { useState, type ReactNode } from 'react';
import { Compass, History, MessageSquare } from 'lucide-react';
import { ConversationSidebar } from './ConversationSidebar';
import { HistoryNavigator } from './HistoryNavigator';
import { DisplaySettings } from './DisplaySettings';
import type { ThreadingState } from '@/scenes/hooks/useThreading';

interface PlaySidebarProps {
  here: ReactNode;
  threading?: ThreadingState;
  onThreadClick: (key: string) => void;
  onShowAll?: () => void;
  selectedThreadKey?: string;
  onOpenReference?: (ref: {
    kind: string;
    key: string;
    title: string;
    poseId?: string;
    timestamp?: string;
  }) => void;
}

/** The one contextual sidebar for the narrative play workspace. */
export function PlaySidebar({
  here,
  threading,
  onThreadClick,
  onShowAll,
  selectedThreadKey,
  onOpenReference,
}: PlaySidebarProps) {
  const [mode, setMode] = useState<'here' | 'conversations' | 'history'>(
    threading ? 'conversations' : 'here'
  );
  return (
    <aside className="flex h-full min-h-0 flex-col" aria-label="Play sidebar">
      <nav className="grid shrink-0 grid-cols-3 gap-1 border-b p-2" aria-label="Sidebar modes">
        <button
          type="button"
          aria-current={mode === 'here' ? 'page' : undefined}
          onClick={() => setMode('here')}
          className={`flex min-h-10 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'here' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
        >
          <Compass className="h-3.5 w-3.5" />
          Here
        </button>
        <button
          type="button"
          aria-current={mode === 'conversations' ? 'page' : undefined}
          onClick={() => setMode('conversations')}
          className={`flex min-h-10 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'conversations' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Conversations
        </button>
        <button
          type="button"
          aria-current={mode === 'history' ? 'page' : undefined}
          onClick={() => setMode('history')}
          className={`flex min-h-10 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'history' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
        >
          <History className="h-3.5 w-3.5" />
          History
        </button>
      </nav>
      <div className="shrink-0 px-2 pb-1">
        <DisplaySettings />
      </div>
      <div
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
        data-testid="play-sidebar-scroll"
      >
        {mode === 'here' && here}
        {mode === 'conversations' && (
          <ConversationSidebar
            threading={threading}
            onThreadClick={onThreadClick}
            onShowAll={onShowAll}
            selectedThreadKey={selectedThreadKey}
          />
        )}
        {mode === 'history' && <HistoryNavigator onOpenReference={onOpenReference} />}
      </div>
    </aside>
  );
}
