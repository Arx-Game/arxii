/**
 * JournalsPage — `/journals` (#2160).
 *
 * Two sections: "My Journal" (`mine/`, includes private entries, with a
 * "Write" button opening `JournalComposerDialog`) and "Public Journals" (the
 * public feed, filterable by author id / tag name, paginated). Rows expand
 * in place to the full entry — body, tags, and (public entries) a
 * Praise/Retort response form plus existing responses.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import type { JournalEntrySummary, JournalResponseType } from '../api';
import {
  useJournalEntries,
  useJournalEntry,
  useMyJournalEntries,
  useRespondToJournal,
} from '../queries';
import { JournalComposerDialog } from '../components/JournalComposerDialog';

export function JournalsPage() {
  const [composerOpen, setComposerOpen] = useState(false);

  return (
    <div className="container mx-auto max-w-3xl space-y-8 px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Journals</h1>
        <Button onClick={() => setComposerOpen(true)}>Write</Button>
      </div>

      <MyJournalSection />
      <PublicJournalsSection />

      <JournalComposerDialog open={composerOpen} onClose={() => setComposerOpen(false)} />
    </div>
  );
}

function MyJournalSection() {
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const { data, isLoading } = useMyJournalEntries(page);
  const entries = data?.results ?? [];

  return (
    <section className="space-y-3" data-testid="my-journal-section">
      <h2 className="text-lg font-medium">My Journal</h2>
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">You haven&apos;t written anything yet.</p>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <EntryRow
              key={entry.id}
              entry={entry}
              expanded={expandedId === entry.id}
              onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
              showResponseForm={false}
            />
          ))}
        </div>
      )}
      <PaginationControls
        page={page}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => p + 1)}
        hasNext={!!data?.next}
        hasPrev={!!data?.previous}
      />
    </section>
  );
}

function PublicJournalsSection() {
  const [page, setPage] = useState(1);
  const [authorFilter, setAuthorFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const author = authorFilter.trim() ? Number(authorFilter.trim()) : undefined;
  const tag = tagFilter.trim() || undefined;

  const { data, isLoading } = useJournalEntries({ page, author, tag: tag || undefined });
  const entries = data?.results ?? [];

  return (
    <section className="space-y-3" data-testid="public-journals-section">
      <h2 className="text-lg font-medium">Public Journals</h2>
      <div className="flex flex-wrap gap-2">
        <div className="space-y-1">
          <Label htmlFor="filter-author">Author (character id)</Label>
          <Input
            id="filter-author"
            value={authorFilter}
            onChange={(e) => {
              setAuthorFilter(e.target.value);
              setPage(1);
            }}
            placeholder="e.g. 42"
            className="w-40"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="filter-tag">Tag</Label>
          <Input
            id="filter-tag"
            value={tagFilter}
            onChange={(e) => {
              setTagFilter(e.target.value);
              setPage(1);
            }}
            placeholder="e.g. grief"
            className="w-40"
          />
        </div>
      </div>
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No public entries found.</p>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <EntryRow
              key={entry.id}
              entry={entry}
              expanded={expandedId === entry.id}
              onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
              showResponseForm
            />
          ))}
        </div>
      )}
      <PaginationControls
        page={page}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => p + 1)}
        hasNext={!!data?.next}
        hasPrev={!!data?.previous}
      />
    </section>
  );
}

function PaginationControls({
  page,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  page: number;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  if (!hasPrev && !hasNext) return null;
  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={onPrev} disabled={!hasPrev}>
        Previous
      </Button>
      <span className="text-sm text-muted-foreground">Page {page}</span>
      <Button variant="outline" size="sm" onClick={onNext} disabled={!hasNext}>
        Next
      </Button>
    </div>
  );
}

function EntryRow({
  entry,
  expanded,
  onToggle,
  showResponseForm,
}: {
  entry: JournalEntrySummary;
  expanded: boolean;
  onToggle: () => void;
  showResponseForm: boolean;
}) {
  return (
    <Card>
      <button type="button" className="block w-full text-left" onClick={onToggle}>
        <CardHeader className="p-4">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-base">{entry.title}</CardTitle>
            {!entry.is_public ? <Badge variant="outline">Private</Badge> : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{entry.author_name}</span>
            <span>·</span>
            <span>{new Date(entry.created_at).toLocaleDateString()}</span>
            {entry.response_count > 0 ? (
              <>
                <span>·</span>
                <span>
                  {entry.response_count} response{entry.response_count === 1 ? '' : 's'}
                </span>
              </>
            ) : null}
            {entry.tags.map((tag) => (
              <Badge key={tag.id} variant="secondary">
                {tag.name}
              </Badge>
            ))}
          </div>
        </CardHeader>
      </button>
      {expanded ? (
        <CardContent className="p-4 pt-0">
          <EntryDetail entryId={entry.id} showResponseForm={showResponseForm} />
        </CardContent>
      ) : null}
    </Card>
  );
}

function EntryDetail({
  entryId,
  showResponseForm,
}: {
  entryId: number;
  showResponseForm: boolean;
}) {
  const { data: detail, isLoading } = useJournalEntry(entryId);

  if (isLoading || !detail) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-4">
      <p className="whitespace-pre-wrap text-sm">{detail.body}</p>

      {detail.responses.length > 0 ? (
        <div className="space-y-2 border-l-2 pl-3">
          {detail.responses.map((response) => (
            <div key={response.id} className="text-sm">
              <span className="font-medium">{response.author_name}</span>{' '}
              <Badge variant={response.response_type === 'praise' ? 'default' : 'destructive'}>
                {response.response_type}
              </Badge>
              <p className="mt-0.5">{response.title}</p>
            </div>
          ))}
        </div>
      ) : null}

      {showResponseForm ? <RespondForm entryId={entryId} /> : null}
    </div>
  );
}

function RespondForm({ entryId }: { entryId: number }) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const respond = useRespondToJournal();

  function submit(responseType: JournalResponseType) {
    if (!title.trim() || !body.trim() || respond.isPending) return;
    respond.mutate(
      { entryId, body: { title: title.trim(), body, response_type: responseType } },
      {
        onSuccess: () => {
          toast.success(responseType === 'praise' ? 'Praise sent.' : 'Retort sent.');
          setTitle('');
          setBody('');
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to respond');
        },
      }
    );
  }

  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && !respond.isPending;

  return (
    <div className="space-y-2 border-t pt-3">
      <Label htmlFor={`respond-title-${entryId}`}>Respond</Label>
      <Input
        id={`respond-title-${entryId}`}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="A title for your response"
      />
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Praise or retort…"
      />
      <div className="flex gap-2">
        <Button size="sm" disabled={!canSubmit} onClick={() => submit('praise')}>
          Praise
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={!canSubmit}
          onClick={() => submit('retort')}
        >
          Retort
        </Button>
      </div>
    </div>
  );
}
