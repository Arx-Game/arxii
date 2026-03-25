import type { Thread } from '../hooks/useThreading';
import { cn } from '@/lib/utils';

interface ThreadSidebarProps {
  threads: Thread[];
  selectedThreadKey: string;
  enabledThreadKeys: Set<string>;
  isUnfiltered: boolean;
  onThreadClick: (key: string) => void;
  onShowAll: () => void;
  onOpenFilter: (threadKey: string) => void;
}

function allPersonaNames(thread: Thread): string {
  return thread.participantPersonas.map((p) => p.name).join(', ');
}

export function ThreadSidebar({
  threads,
  selectedThreadKey,
  enabledThreadKeys,
  isUnfiltered,
  onThreadClick,
  onShowAll,
  onOpenFilter,
}: ThreadSidebarProps) {
  return (
    <nav className="flex w-44 shrink-0 flex-col gap-1 border-r pr-2" aria-label="Thread sidebar">
      <button
        className={cn(
          'rounded px-2 py-1 text-left text-sm font-medium',
          isUnfiltered ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted'
        )}
        onClick={onShowAll}
      >
        All
      </button>

      {threads.map((thread) => {
        const isEnabled = enabledThreadKeys.has(thread.key);
        const isSelected = selectedThreadKey === thread.key;
        const showTooltip = thread.participantPersonas.length > 3;

        return (
          <button
            key={thread.key}
            className={cn(
              'flex items-center justify-between rounded px-2 py-1 text-left text-sm',
              isEnabled && 'bg-accent text-accent-foreground',
              isSelected && 'font-semibold',
              !isEnabled && !isUnfiltered && 'text-muted-foreground/50',
              !isEnabled && isUnfiltered && 'text-muted-foreground hover:bg-muted'
            )}
            title={showTooltip ? allPersonaNames(thread) : undefined}
            onClick={() => onThreadClick(thread.key)}
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
