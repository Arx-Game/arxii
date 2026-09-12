import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, History, CalendarDays } from 'lucide-react';
import { fetchPlayConversations, fetchPlaySearch } from '../playQueries';
import { ConversationThreadList } from './ConversationThreadList';
import type { ThreadSummary } from '../playTypes';

interface HistoryNavigatorProps {
  onOpenReference?: (ref: {
    kind: string;
    key: string;
    title: string;
    poseId?: string;
    timestamp?: string;
  }) => void;
}

// Hoisted to module scope so each class string fits the 100-char line limit on
// its own; Prettier reflows an inline multi-line JSX attribute back into one
// long line, which it will not then re-wrap (see ConversationThreadList.tsx's
// own ROW_BUTTON_CLASS for the same pattern).
const CONVERSATION_TITLE_BUTTON_CLASS = 'block w-full text-left text-sm disabled:opacity-50';
const THREADS_TOGGLE_CLASS =
  'mt-1 flex w-full items-center justify-between border-t border-dotted pt-1 ' +
  'text-xs text-primary';

/**
 * The Threads control's own label. `count` is `undefined` until the list has
 * actually been opened once (see the no-eager-count comment at the call site),
 * so a collapsed row (or one never yet opened) always reads plain "Threads".
 */
function threadsToggleLabel(isExpanded: boolean, count: number | undefined): string {
  if (!isExpanded || count === undefined) return 'Threads';
  if (count === 0) return 'No reply threads';
  return `${count} ${count === 1 ? 'thread' : 'threads'}`;
}

/** Search and browse authorized retained conversations without leaving /game. */
export function HistoryNavigator({ onOpenReference }: HistoryNavigatorProps) {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [kind, setKind] = useState<'all' | 'room' | 'whisper'>('all');
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [conversationsCursor, setConversationsCursor] = useState<string | undefined>(undefined);
  // At most one conversation's threads are open at a time: the three sidebar
  // modes share one scroll container, and several expanded lists at once turn
  // the History pane into a wall of nested lists (#3772).
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [threadCounts, setThreadCounts] = useState<Record<string, number>>({});
  const ninetyDaysAgo = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 90);
    return d.toISOString().slice(0, 10);
  }, []);
  const conversations = useQuery({
    queryKey: ['play-conversations', from, to, showAllHistory, conversationsCursor],
    queryFn: () =>
      fetchPlayConversations({
        from: from || (showAllHistory ? undefined : ninetyDaysAgo),
        to: to || undefined,
        after: conversationsCursor,
      }),
    staleTime: 30_000,
  });
  const search = useQuery({
    queryKey: ['play-search', submitted, from, to, kind],
    queryFn: () =>
      fetchPlaySearch(
        submitted,
        from || ninetyDaysAgo,
        to || undefined,
        kind === 'all' ? undefined : kind
      ),
    enabled: submitted.length >= 2,
    staleTime: 30_000,
  });
  return (
    <div className="space-y-4 p-3" data-testid="history-navigator">
      <div>
        <h2 className="flex items-center gap-2 font-serif text-lg">
          <History className="h-4 w-4" /> History
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Find authorized scenes, whispers, and communications.
        </p>
      </div>
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query.trim());
        }}
      >
        <label className="sr-only" htmlFor="history-search">
          Search history
        </label>
        <div className="flex gap-2">
          <input
            id="history-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search history"
            className="min-w-0 flex-1 rounded border bg-background px-2 py-2 text-sm"
          />
          <button type="submit" aria-label="Search history" className="rounded border px-3">
            <Search className="h-4 w-4" />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-muted-foreground">
            From
            <input
              type="date"
              value={from}
              onChange={(event) => {
                setFrom(event.target.value);
                // #3759 review fix, fold-in: reset paging back to page 1 the
                // instant the filter that actually scopes the conversations
                // query changes (see its `queryKey` below -- `kind` only
                // scopes `search`), synchronously with the change rather than
                // one render later via an effect.
                setConversationsCursor(undefined);
              }}
              className="mt-1 block w-full rounded border bg-background px-2 py-1 text-sm"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            To
            <input
              type="date"
              value={to}
              onChange={(event) => {
                setTo(event.target.value);
                setConversationsCursor(undefined);
              }}
              className="mt-1 block w-full rounded border bg-background px-2 py-1 text-sm"
            />
          </label>
        </div>
        <label className="text-xs text-muted-foreground">
          Type
          <select
            aria-label="Type"
            value={kind}
            onChange={(event) => setKind(event.target.value as typeof kind)}
            className="mt-1 block w-full rounded border bg-background px-2 py-1 text-sm"
          >
            <option value="all">All accessible</option>
            <option value="room">Scenes</option>
            <option value="whisper">Whispers</option>
          </select>
        </label>
      </form>
      {search.isLoading && <p className="text-sm text-muted-foreground">Searching…</p>}
      {submitted.length >= 2 && !search.isLoading && search.data?.results.length === 0 && (
        <p className="text-sm text-muted-foreground">No accessible matches.</p>
      )}
      {search.data?.results.map((result) => (
        <button
          key={`${result.pose.id}:${result.pose.timestamp}`}
          type="button"
          className="block w-full rounded border p-2 text-left hover:bg-accent"
          onClick={() =>
            onOpenReference?.({
              kind: result.conversation.kind,
              key: result.conversation.key,
              title: result.title,
              poseId: result.pose.id,
              timestamp: result.pose.timestamp,
            })
          }
        >
          <span className="block text-sm font-medium">{result.title}</span>
          <span className="mt-1 block text-xs text-muted-foreground">{result.excerpt}</span>
        </button>
      ))}
      <div className="border-t pt-3">
        <button
          type="button"
          className="mb-2 text-xs underline"
          onClick={() => {
            setShowAllHistory((v) => !v);
            setConversationsCursor(undefined);
          }}
        >
          {showAllHistory ? 'Show recent only' : 'Show all my accessible history'}
        </button>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
          <CalendarDays className="h-3 w-3" /> Recent conversations
        </h3>
        {conversations.isLoading && (
          <p className="mt-2 text-sm text-muted-foreground">Loading history…</p>
        )}
        {conversations.data?.results.map((conversation) => {
          const key = `${conversation.ref.kind}:${conversation.ref.key}`;
          const isExpanded = expandedKey === key;
          const count = threadCounts[key];
          return (
            <div key={key} className="mt-2 rounded border p-2">
              <button
                type="button"
                disabled={!conversation.canRead}
                className={CONVERSATION_TITLE_BUTTON_CLASS}
                onClick={() =>
                  onOpenReference?.({
                    ...conversation.ref,
                    title: conversation.title,
                    poseId: conversation.latestVisiblePose?.id,
                    timestamp: conversation.latestVisiblePose?.timestamp,
                  })
                }
              >
                <span className="block font-medium">{conversation.title}</span>
                <span className="text-xs text-muted-foreground">
                  {conversation.unread ? `${conversation.unread} new · ` : ''}
                  {conversation.availability === 'temporary' ? 'Temporary · not saved' : 'Retained'}
                </span>
              </button>
              {conversation.canRead && (
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  className={THREADS_TOGGLE_CLASS}
                  onClick={() => setExpandedKey(isExpanded ? null : key)}
                >
                  {/* No count until the list has been opened: a count on every
                      collapsed row means asking the server about all thirty
                      visible conversations before anyone has shown interest in
                      one (#3772 spec decision 4). */}
                  <span>{threadsToggleLabel(isExpanded, count)}</span>
                  <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
                </button>
              )}
              {isExpanded && (
                <ConversationThreadList
                  conversationKey={conversation.ref.key}
                  onCountLoaded={(loaded) =>
                    // Identity-preserving updater: bail out to the SAME object when
                    // the count hasn't changed, so the changed-`onCountLoaded`-identity
                    // (an inline arrow, recreated every render) never re-triggers
                    // ConversationThreadList's count effect and spins an infinite
                    // render loop. Do not simplify this back to an unconditional
                    // spread (found in Task 2 review, #3772).
                    setThreadCounts((current) =>
                      current[key] === loaded ? current : { ...current, [key]: loaded }
                    )
                  }
                  onOpenThread={(thread: ThreadSummary) =>
                    onOpenReference?.({
                      ...conversation.ref,
                      title: conversation.title,
                      poseId: thread.firstVisible.id,
                      timestamp: thread.firstVisible.timestamp,
                    })
                  }
                />
              )}
            </div>
          );
        })}
        {!conversations.isLoading && !conversations.data?.results.length && (
          <p className="mt-2 text-sm text-muted-foreground">No earlier conversations.</p>
        )}
        {conversations.data?.after && (
          <button
            type="button"
            className="mt-2 block w-full rounded border p-2 text-center text-sm hover:bg-accent"
            onClick={() => setConversationsCursor(conversations.data?.after ?? undefined)}
          >
            {/* "Next page" (#3759 review fold-in), not "Load more" -- this
                REPLACES the current page rather than appending to it (only
                conversations.data?.results renders), which "Load more" would
                misleadingly imply. Accumulating via useInfiniteQuery would be
                a bigger change than this fold-in warrants. */}
            Next page
          </button>
        )}
      </div>
    </div>
  );
}
