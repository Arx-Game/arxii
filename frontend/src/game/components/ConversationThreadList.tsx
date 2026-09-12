import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchPlayThreads } from '../playQueries';
import type { ThreadSummary } from '../playTypes';

interface ConversationThreadListProps {
  /** The conversation ref key the endpoint is bound to, for example `scene:412`. */
  conversationKey: string;
  onOpenThread: (thread: ThreadSummary) => void;
  /** Reported after each successful page so the caller can label its control. */
  onCountLoaded?: (count: number) => void;
}

const OPENING_LABEL_LIMIT = 60;

// Hoisted to module scope (rather than inlined in JSX) so each class string fits the
// 100-char line limit on its own; Prettier reflows an inline multi-line JSX attribute
// back into one long line, which it will not then re-wrap.
const ROW_BUTTON_CLASS =
  'flex w-full items-start justify-between gap-2 rounded bg-accent/40 px-2 py-1 ' +
  'text-left hover:bg-accent';
const UNREAD_PILL_CLASS =
  'ml-1 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full ' +
  'bg-primary px-1 text-xs text-primary-foreground';

function shortDate(timestamp: string): string {
  return new Date(timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * A thread's label is its own opening line, which is how the reader titles a
 * thread (`ThreadedNarrativeReader.tsx`, and the approved #3759 demo's own
 * `paras[0].slice(0, 60)`), so the same thread reads the same in both places.
 * `opening` arrives empty when the root pose is blanked for a muted persona
 * (#2087) or is in a language this viewer does not comprehend (#2993), so the
 * row falls back to what it can still say truthfully rather than rendering an
 * unlabelled button.
 */
function threadLabel(thread: ThreadSummary): string {
  const opening = thread.opening.trim();
  if (opening) return opening.slice(0, OPENING_LABEL_LIMIT);
  return `${thread.visiblePoseCount} poses from ${shortDate(thread.firstVisible.timestamp)}`;
}

/** One conversation's reply threads, drilled into from the History navigator. */
export function ConversationThreadList({
  conversationKey,
  onOpenThread,
  onCountLoaded,
}: ConversationThreadListProps) {
  // Per-conversation paging state lives here rather than in `HistoryNavigator`,
  // so collapsing a conversation discards its cursor instead of leaking it into
  // the next conversation opened (#3772).
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const threads = useQuery({
    queryKey: ['play-threads', conversationKey, cursor],
    queryFn: () => fetchPlayThreads({ conversation: conversationKey, after: cursor }),
    staleTime: 30_000,
  });
  // `queryFn` only runs on an actual fetch, so a count reported from inside it is
  // skipped whenever `useQuery` serves a cache-warm remount (within `staleTime`)
  // without refetching. An effect keyed on the resolved data fires on every render
  // that has data, cache-served remounts included, so the caller's count label
  // never goes stale after a conversation is collapsed and reopened.
  useEffect(() => {
    if (threads.data) onCountLoaded?.(threads.data.results.length);
  }, [threads.data, onCountLoaded]);
  return (
    <div
      className="ml-2 mt-2 space-y-1 border-l-2 pl-2"
      data-testid={`thread-list-${conversationKey}`}
    >
      {threads.isLoading && <p className="text-xs text-muted-foreground">Loading threads…</p>}
      {threads.isError && (
        <p className="text-xs text-muted-foreground">Threads are unavailable right now.</p>
      )}
      {threads.data?.results.map((thread) => (
        <button
          key={thread.id}
          type="button"
          className={ROW_BUTTON_CLASS}
          onClick={() => onOpenThread(thread)}
        >
          <span className="min-w-0">
            <span className="block text-sm italic">{threadLabel(thread)}</span>
            <span className="block text-xs text-muted-foreground">
              {thread.visiblePoseCount} poses · {shortDate(thread.firstVisible.timestamp)}
            </span>
          </span>
          {thread.unread > 0 && <span className={UNREAD_PILL_CLASS}>{thread.unread}</span>}
        </button>
      ))}
      {threads.data && !threads.data.results.length && (
        <p className="px-2 py-1 text-xs italic text-muted-foreground">
          {/* The approved demo's own wording for this state. Do not reword it
              without rebuilding the demo: the demo is the approved design. */}
          Every pose here stands on its own. Open the conversation to read it.
        </p>
      )}
      {threads.data?.after && (
        <button
          type="button"
          className="block w-full rounded border p-1 text-center text-xs hover:bg-accent"
          onClick={() => setCursor(threads.data?.after ?? undefined)}
        >
          {/* "Next page", like the conversation pager above it: this REPLACES the
              current page rather than appending to it. */}
          Next page
        </button>
      )}
    </div>
  );
}
