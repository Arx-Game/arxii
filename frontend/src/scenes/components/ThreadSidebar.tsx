import type { Thread } from '../hooks/useThreading';
import { cn } from '@/lib/utils';

interface ThreadSidebarProps {
  threads: Thread[];
  activeThreadKey: string;
  visibleThreadKeys: Set<string>;
  showingAll: boolean;
  onToggleThread: (key: string) => void;
  onSelectThread: (key: string) => void;
  onShowAll: () => void;
  onOpenFilter: (threadKey: string) => void;
}

function allPersonaNames(thread: Thread): string {
  return thread.participantPersonas.map((p) => p.name).join(', ');
}

export function ThreadSidebar({
  threads,
  activeThreadKey,
  visibleThreadKeys,
  showingAll,
  onToggleThread,
  onSelectThread,
  onShowAll,
  onOpenFilter,
}: ThreadSidebarProps) {
  return (
    <nav className="flex w-44 shrink-0 flex-col gap-1 border-r pr-2" aria-label="Thread sidebar">
      <button
        className={cn(
          'rounded px-2 py-1 text-left text-sm font-medium',
          showingAll ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted'
        )}
        onClick={onShowAll}
      >
        All
      </button>

      {threads.map((thread) => {
        const isVisible = visibleThreadKeys.has(thread.key);
        const isActive = activeThreadKey === thread.key;
        const showTooltip = thread.participantPersonas.length > 3;

        return (
          <button
            key={thread.key}
            className={cn(
              'flex items-center justify-between rounded px-2 py-1 text-left text-sm',
              isVisible && 'bg-accent text-accent-foreground',
              isActive && 'font-semibold',
              !isVisible && !showingAll && 'text-muted-foreground/50',
              !isVisible && showingAll && 'text-muted-foreground hover:bg-muted'
            )}
            title={showTooltip ? allPersonaNames(thread) : undefined}
            onClick={() => {
              onSelectThread(thread.key);
              onToggleThread(thread.key);
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              onOpenFilter(thread.key);
            }}
          >
            <span className="truncate">{thread.label}</span>
            {thread.unreadCount > 0 && (
              <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs text-primary-foreground">
                {thread.unreadCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
