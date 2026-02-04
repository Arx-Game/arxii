import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, Loader2, BookOpen, Lock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useCodexTree, useCodexEntries, useCodexEntry, useCodexSearch } from '../queries';
import { CodexTree } from '../components/CodexTree';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { CodexEntryListItem, CodexEntryDetail } from '../types';

export function CodexPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const selectedSubjectId = searchParams.get('subject')
    ? parseInt(searchParams.get('subject')!, 10)
    : undefined;
  const selectedEntryId = searchParams.get('entry')
    ? parseInt(searchParams.get('entry')!, 10)
    : undefined;

  const { data: tree, isLoading: treeLoading } = useCodexTree();
  const { data: entries } = useCodexEntries(selectedSubjectId);
  const { data: selectedEntry, isLoading: entryLoading } = useCodexEntry(selectedEntryId ?? 0);
  const { data: searchResults, isLoading: searchLoading } = useCodexSearch(debouncedSearch);

  const handleSelectSubject = (subjectId: number) => {
    setSearchParams({ subject: subjectId.toString() });
    setSearchInput('');
  };

  const handleSelectEntry = (entryId: number) => {
    const currentSubject = searchParams.get('subject');
    const params: Record<string, string> = { entry: entryId.toString() };
    if (currentSubject) params.subject = currentSubject;
    setSearchParams(params);
    setSearchInput('');
  };

  const showSearchResults = debouncedSearch.length >= 2;

  return (
    <div className="flex gap-6">
      {/* Sidebar */}
      <aside className="w-64 shrink-0">
        <div className="sticky top-4 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search codex..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-8"
            />
          </div>

          {/* Search Results or Tree */}
          {showSearchResults ? (
            <div className="space-y-1">
              <div className="text-sm font-medium text-muted-foreground">Search Results</div>
              {searchLoading ? (
                <div className="flex items-center gap-2 py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Searching...</span>
                </div>
              ) : searchResults?.length === 0 ? (
                <div className="py-2 text-sm text-muted-foreground">No results found</div>
              ) : (
                searchResults?.map((entry) => (
                  <SearchResultItem
                    key={entry.id}
                    entry={entry}
                    onClick={() => handleSelectEntry(entry.id)}
                  />
                ))
              )}
            </div>
          ) : treeLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="ml-4 h-6 w-3/4" />
              <Skeleton className="ml-4 h-6 w-3/4" />
            </div>
          ) : tree ? (
            <CodexTree
              categories={tree}
              selectedEntryId={selectedEntryId}
              onSelectSubject={handleSelectSubject}
              onSelectEntry={handleSelectEntry}
            />
          ) : null}
        </div>
      </aside>

      {/* Main Content */}
      <main className="min-w-0 flex-1">
        {selectedEntryId ? (
          entryLoading ? (
            <Card>
              <CardHeader>
                <Skeleton className="h-8 w-1/2" />
              </CardHeader>
              <CardContent>
                <Skeleton className="mb-2 h-4 w-full" />
                <Skeleton className="mb-2 h-4 w-3/4" />
                <Skeleton className="h-4 w-5/6" />
              </CardContent>
            </Card>
          ) : selectedEntry ? (
            <EntryDetail entry={selectedEntry} />
          ) : null
        ) : entries?.length ? (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Entries</h2>
            <div className="grid gap-4">
              {entries.map((entry) => (
                <EntryCard
                  key={entry.id}
                  entry={entry}
                  onClick={() => handleSelectEntry(entry.id)}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <BookOpen className="mb-4 h-12 w-12 text-muted-foreground" />
            <h2 className="mb-2 text-xl font-semibold">Welcome to the Codex</h2>
            <p className="max-w-md text-muted-foreground">
              Browse the knowledge base using the tree on the left, or search for specific topics.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

function SearchResultItem({ entry, onClick }: { entry: CodexEntryListItem; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full rounded px-2 py-1.5 text-left hover:bg-accent">
      <div className="text-sm font-medium">{entry.name}</div>
      <div className="truncate text-xs text-muted-foreground">{entry.subject_path.join(' > ')}</div>
    </button>
  );
}

function EntryCard({ entry, onClick }: { entry: CodexEntryListItem; onClick: () => void }) {
  return (
    <Card className="cursor-pointer transition-colors hover:bg-accent/50" onClick={onClick}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-lg">{entry.name}</CardTitle>
          {entry.knowledge_status === 'uncovered' && (
            <Badge variant="outline">
              <Lock className="mr-1 h-3 w-3" />
              Researching
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{entry.summary}</p>
      </CardContent>
    </Card>
  );
}

function EntryDetail({ entry }: { entry: CodexEntryDetail }) {
  const isUncovered = entry.knowledge_status === 'uncovered';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>{entry.name}</CardTitle>
          {isUncovered && (
            <Badge variant="outline">
              <Lock className="mr-1 h-3 w-3" />
              Researching
            </Badge>
          )}
        </div>
        <div className="text-sm text-muted-foreground">{entry.subject_path.join(' > ')}</div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isUncovered && entry.research_progress !== null && entry.learn_threshold && (
          <div className="rounded-lg bg-muted p-3">
            <div className="mb-1 text-sm font-medium">Research Progress</div>
            <div className="flex items-center gap-2">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                <div
                  className="h-full bg-primary"
                  style={{
                    width: `${Math.min(100, (entry.research_progress / entry.learn_threshold) * 100)}%`,
                  }}
                />
              </div>
              <span className="text-sm text-muted-foreground">
                {entry.research_progress}/{entry.learn_threshold}
              </span>
            </div>
          </div>
        )}
        {entry.content ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            {entry.content.split('\n').map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))}
          </div>
        ) : (
          <div className="italic text-muted-foreground">
            {entry.summary}
            <p className="mt-2 text-sm">Continue researching to uncover the full content.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
