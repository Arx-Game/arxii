import type { Thread, ThreadHubSummary } from '../../types';
import { ThreadStateBadge } from './ThreadStateBadge';

type ThreadState = 'ready' | 'near_xp_lock' | 'blocked' | 'normal';

interface ThreadCardProps {
  thread: Thread;
  summary: ThreadHubSummary;
  onClick: (thread: Thread) => void;
}

/**
 * Derive the badge state for a thread from summary membership.
 * Priority: blocked > near_xp_lock > ready > normal.
 */
function deriveThreadState(threadId: number, summary: ThreadHubSummary): ThreadState {
  if (summary.blocked_thread_ids.includes(threadId)) {
    return 'blocked';
  }
  const nearXpLockIds = summary.near_xp_lock_thread_ids.map((p) => p.thread_id);
  if (nearXpLockIds.includes(threadId)) {
    return 'near_xp_lock';
  }
  if (summary.ready_thread_ids.includes(threadId)) {
    return 'ready';
  }
  return 'normal';
}

/**
 * A single thread row card with state badge and anchor display.
 * Click anywhere on the card to navigate to the thread detail page.
 */
export function ThreadCard({ thread, summary, onClick }: ThreadCardProps) {
  const state = deriveThreadState(thread.id, summary);
  const displayName = thread.name.trim() || '(unnamed)';
  const displayLevel = thread.level / 10;

  return (
    <button
      type="button"
      className="w-full rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => onClick(thread)}
      data-testid={`thread-card-${thread.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 overflow-hidden">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium">{displayName}</span>
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {thread.target_kind}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>Level {displayLevel}</span>
            <span>{thread.resonance_name}</span>
          </div>
        </div>
        <div className="shrink-0">
          <ThreadStateBadge state={state} />
        </div>
      </div>
    </button>
  );
}
