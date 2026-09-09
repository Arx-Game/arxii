import { useState } from 'react';
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
  const conversations = useQuery({
    queryKey: ['play-conversations', from, to],
    queryFn: () => fetchPlayConversations({ from: from || undefined, to: to || undefined }),
    staleTime: 30_000,
  });
  const search = useQuery({
    queryKey: ['play-search', submitted, from, to],
    queryFn: () => fetchPlaySearch(submitted, from || undefined, to || undefined),
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
      </div>
    </div>
  );
}
