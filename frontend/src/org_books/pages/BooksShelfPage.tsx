/**
 * BooksShelfPage — the organizations whose books the viewer may open.
 *
 * Diegetic posture: this is your own shelf, never a browse of all orgs.
 * Each card links to /books/:orgId (the family-books screen).
 */

import { Link } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { MyBooksRow } from '@/org_books/api';
import { useMyBooksShelf } from '@/org_books/queries';

function ShelfSkeleton() {
  return (
    <div className="space-y-3" data-testid="books-shelf-skeleton">
      {[0, 1].map((i) => (
        <div key={i} className="animate-pulse rounded-lg border bg-card p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-24" />
            </div>
            <Skeleton className="h-8 w-24 shrink-0" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ShelfCard({ row }: { row: MyBooksRow }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold">{row.organization_name}</span>
              <Badge variant="outline" className="shrink-0 text-xs">
                {row.rank_title}
              </Badge>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">Rank {row.rank}</p>
          </div>
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <Link to={`/books/${row.organization_id}`}>Open the books</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ShelfInner() {
  const { data, isLoading } = useMyBooksShelf();

  if (isLoading) return <ShelfSkeleton />;

  const rows = data ?? [];
  if (rows.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="books-shelf-empty">
        You hold no position that opens an organization&apos;s books.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="books-shelf">
      {rows.map((row) => (
        <ShelfCard key={row.organization_id} row={row} />
      ))}
    </div>
  );
}

export function BooksShelfPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">The Books</h1>
      <ErrorBoundary>
        <ShelfInner />
      </ErrorBoundary>
    </div>
  );
}
