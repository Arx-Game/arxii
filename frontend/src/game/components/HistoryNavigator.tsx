import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, History, CalendarDays } from 'lucide-react';
import { fetchPlayConversations, fetchPlaySearch } from '../playQueries';

interface HistoryNavigatorProps {
  onOpenReference?: (ref: {
    kind: string;
    key: string;
    title: string;
    poseId?: string;
    timestamp?: string;
  }) => void;
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
  // #3759 review fix: `from`/`to` are the filters that actually scope the
  // conversations query (see its `queryKey` below — `kind` only scopes
  // `search`, not `conversations`). Without this, paging forward with
  // "Load more" was a one-way trap: only the showAllHistory toggle reset the
  // cursor, so changing a date filter mid-page silently kept requesting page
  // N+1 of the OLD filter instead of returning to page 1 of the new one.
  // Skip the very first render (mount) so this never fires on initial values.
  const isFirstDateFilterRender = useRef(true);
  useEffect(() => {
    if (isFirstDateFilterRender.current) {
      isFirstDateFilterRender.current = false;
      return;
    }
    setConversationsCursor(undefined);
  }, [from, to]);
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
              onChange={(event) => setFrom(event.target.value)}
              className="mt-1 block w-full rounded border bg-background px-2 py-1 text-sm"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            To
            <input
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
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
        {conversations.data?.results.map((conversation) => (
          <button
            key={`${conversation.ref.kind}:${conversation.ref.key}`}
            type="button"
            disabled={!conversation.canRead}
            className="mt-2 block w-full rounded border p-2 text-left text-sm disabled:opacity-50"
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
        ))}
        {!conversations.isLoading && !conversations.data?.results.length && (
          <p className="mt-2 text-sm text-muted-foreground">No earlier conversations.</p>
        )}
        {conversations.data?.after && (
          <button
            type="button"
            className="mt-2 block w-full rounded border p-2 text-center text-sm hover:bg-accent"
            onClick={() => setConversationsCursor(conversations.data?.after ?? undefined)}
          >
            Load more
          </button>
        )}
      </div>
    </div>
  );
}
