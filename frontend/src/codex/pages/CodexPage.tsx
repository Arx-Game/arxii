import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useCodexTree, useCodexSearch } from '../queries';
import { CodexTree } from '../components/CodexTree';
import { CodexContent } from '../components/CodexContent';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { CodexEntryListItem } from '../types';

export function CodexPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const categoryId = searchParams.get('category')
    ? parseInt(searchParams.get('category')!, 10)
    : undefined;
  const subjectId = searchParams.get('subject')
    ? parseInt(searchParams.get('subject')!, 10)
    : undefined;
  const entryId = searchParams.get('entry') ? parseInt(searchParams.get('entry')!, 10) : undefined;

  const { data: tree, isLoading: treeLoading } = useCodexTree();
  const { data: searchResults, isLoading: searchLoading } = useCodexSearch(debouncedSearch);

  const handleSelectCategory = useCallback(
    (id: number) => {
      setSearchParams({ category: id.toString() });
      setSearchInput('');
    },
    [setSearchParams]
  );

  const handleSelectSubject = useCallback(
    (id: number) => {
      setSearchParams({ subject: id.toString() });
      setSearchInput('');
    },
    [setSearchParams]
  );

  const handleSelectEntry = useCallback(
    (id: number) => {
      const params: Record<string, string> = { entry: id.toString() };
      if (subjectId) params.subject = subjectId.toString();
      setSearchParams(params);
      setSearchInput('');
    },
    [setSearchParams, subjectId]
  );

  const handleNavigateBreadcrumb = useCallback(
    (type: 'home' | 'category' | 'subject', id?: number) => {
      if (type === 'home') {
        setSearchParams({});
      } else if (type === 'category' && id) {
        setSearchParams({ category: id.toString() });
      } else if (type === 'subject' && id) {
        setSearchParams({ subject: id.toString() });
      }
    },
    [setSearchParams]
  );

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
              selectedCategoryId={categoryId}
              selectedSubjectId={subjectId}
              selectedEntryId={entryId}
              onSelectCategory={handleSelectCategory}
              onSelectSubject={handleSelectSubject}
              onSelectEntry={handleSelectEntry}
            />
          ) : null}
        </div>
      </aside>

      {/* Main Content */}
      <main className="min-w-0 flex-1">
        <CodexContent
          categoryId={categoryId}
          subjectId={subjectId}
          entryId={entryId}
          onSelectCategory={handleSelectCategory}
          onSelectSubject={handleSelectSubject}
          onSelectEntry={handleSelectEntry}
          onNavigateBreadcrumb={handleNavigateBreadcrumb}
        />
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
