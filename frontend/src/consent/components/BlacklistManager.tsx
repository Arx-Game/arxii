import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useBlacklist, useAddBlacklist, useRemoveBlacklist } from '../queries';
import { useTenureSearch } from '@/mail/queries';

interface Props {
  tenureId: number;
  categoryId: number;
}

/** Antagonism blacklist (#1698) — people barred from this category under "Everyone except my
 * blacklist" mode. The blocked party is never told. Mirrors WhitelistManager. */
function BlacklistManagerInner({ tenureId, categoryId }: Props) {
  const [search, setSearch] = useState('');
  const { data: blacklist, isLoading: blacklistLoading } = useBlacklist(tenureId, categoryId);
  const { data: searchResults } = useTenureSearch(search);
  const addBlacklist = useAddBlacklist();
  const removeBlacklist = useRemoveBlacklist();

  if (blacklistLoading) {
    return (
      <div className="mt-2 space-y-2 pl-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-6 w-24" />
      </div>
    );
  }

  const entries = blacklist?.results ?? [];

  return (
    <div className="mt-2 space-y-2 pl-4">
      {entries.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {entries.map((entry) => (
            <span
              key={entry.id}
              className="flex items-center gap-1 rounded-full bg-secondary px-3 py-1 text-sm"
            >
              {entry.blocked_tenure_name ?? entry.blocked_tenure}
              <button
                type="button"
                aria-label={`Remove ${entry.blocked_tenure_name ?? `tenure ${entry.blocked_tenure}`} from blacklist`}
                className="ml-1 text-muted-foreground hover:text-foreground"
                onClick={() =>
                  removeBlacklist.mutate({
                    id: entry.id,
                    ownerTenureId: tenureId,
                    categoryId,
                  })
                }
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No characters on the blacklist yet.</p>
      )}

      <div className="space-y-1">
        <Input
          placeholder="Search character to bar..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {searchResults && searchResults.results.length > 0 && (
          <ul className="max-w-xs rounded border">
            {searchResults.results.map((opt) => (
              <li key={opt.id}>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full justify-start"
                  disabled={
                    addBlacklist.isPending || entries.some((e) => e.blocked_tenure === opt.id)
                  }
                  onClick={() => {
                    addBlacklist.mutate(
                      { owner_tenure: tenureId, blocked_tenure: opt.id, category: categoryId },
                      { onSuccess: () => setSearch('') }
                    );
                  }}
                >
                  {opt.display_name}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function BlacklistManager(props: Props) {
  return (
    <ErrorBoundary>
      <BlacklistManagerInner {...props} />
    </ErrorBoundary>
  );
}
