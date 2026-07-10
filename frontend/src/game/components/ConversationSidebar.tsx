import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { ThreadSidebar } from '@/scenes/components/ThreadSidebar';
import { ThreadFilterModal } from '@/scenes/components/ThreadFilterModal';
import type { ThreadingState } from '@/scenes/hooks/useThreading';

interface ConversationSidebarProps {
  /** The active scene's threading state, composed once by `GamePage` (#2156). Absent with no active scene. */
  threading?: ThreadingState;
  /** Fired with a thread's key when it's clicked — GamePage owns the composer-mode translation. */
  onThreadClick: (key: string) => void;
}

export function ConversationSidebar({ threading, onThreadClick }: ConversationSidebarProps) {
  const [filterThreadKey, setFilterThreadKey] = useState<string | null>(null);

  if (!threading) {
    return (
      <div className="flex flex-col">
        <div className="border-b px-3 py-2">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Conversations</h3>
        </div>
        <div className="flex-1">
          <button className="flex w-full items-center gap-2 bg-accent px-3 py-2 text-sm">
            <MessageSquare className="h-4 w-4" />
            <span className="font-medium">Room</span>
          </button>
        </div>
      </div>
    );
  }

  const filterThread = filterThreadKey
    ? threading.threads.find((t) => t.key === filterThreadKey)
    : undefined;

  return (
    <div className="flex flex-col">
      <div className="border-b px-3 py-2">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">Conversations</h3>
      </div>
      <ThreadSidebar
        threads={threading.threads}
        selectedThreadKey={threading.selectedThreadKey}
        enabledThreadKeys={threading.enabledThreadKeys}
        isUnfiltered={threading.enabledThreadKeys.size === 0}
        onThreadClick={onThreadClick}
        onShowAll={threading.showAll}
        onOpenFilter={setFilterThreadKey}
      />

      {filterThread && filterThreadKey && (
        <ThreadFilterModal
          open={!!filterThreadKey}
          onClose={() => setFilterThreadKey(null)}
          thread={filterThread}
          hiddenPersonaIds={threading.getHiddenPersonaIds(filterThreadKey)}
          onTogglePersona={(id) => threading.togglePersonaHidden(filterThreadKey, id)}
        />
      )}
    </div>
  );
}
