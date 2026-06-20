import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useWhitelist, useAddWhitelist, useRemoveWhitelist } from '../queries';
import { useTenureSearch } from '@/mail/queries';

interface Props {
  tenureId: number;
  categoryId: number;
}

function WhitelistManagerInner({ tenureId, categoryId }: Props) {
  const [search, setSearch] = useState('');
  const { data: whitelist, isLoading: whitelistLoading } = useWhitelist(tenureId, categoryId);
  const { data: searchResults } = useTenureSearch(search);
  const addWhitelist = useAddWhitelist();
  const removeWhitelist = useRemoveWhitelist();

  if (whitelistLoading) {
    return (
      <div className="mt-2 space-y-2 pl-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-6 w-24" />
      </div>
    );
  }

  const entries = whitelist?.results ?? [];

  return (
    <div className="mt-2 space-y-2 pl-4">
      {entries.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {entries.map((entry) => (
            <span
              key={entry.id}
              className="flex items-center gap-1 rounded-full bg-secondary px-3 py-1 text-sm"
            >
              {entry.allowed_tenure_name ?? entry.allowed_tenure}
              <button
                type="button"
                aria-label={`Remove ${entry.allowed_tenure_name ?? `tenure ${entry.allowed_tenure}`} from allowlist`}
                className="ml-1 text-muted-foreground hover:text-foreground"
                onClick={() =>
                  removeWhitelist.mutate({
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
        <p className="text-sm text-muted-foreground">No characters on the allowlist yet.</p>
      )}

      <div className="space-y-1">
        <Input
          placeholder="Search character to add..."
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
                    addWhitelist.isPending || entries.some((e) => e.allowed_tenure === opt.id)
                  }
                  onClick={() => {
                    addWhitelist.mutate(
                      { owner_tenure: tenureId, allowed_tenure: opt.id, category: categoryId },
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

export function WhitelistManager(props: Props) {
  return (
    <ErrorBoundary>
      <WhitelistManagerInner {...props} />
    </ErrorBoundary>
  );
}
