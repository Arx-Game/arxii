/**
 * CovenantsListPage — list of covenants the player has memberships in.
 *
 * Backend scoping: non-staff users only see covenants where they have an
 * active membership (via CharacterCovenantRole chain). Staff see all.
 *
 * Each card shows covenant name, type, sworn_objective, and member count,
 * with a "Detail" CTA linking to /covenants/:id.
 */

import { Link } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useCovenants } from '@/covenants/queries';
import type { Covenant } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function CovenantCardSkeleton() {
  return (
    <div
      className="animate-pulse rounded-lg border bg-card p-4"
      data-testid="covenant-card-skeleton"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-full" />
        </div>
        <Skeleton className="h-8 w-16 shrink-0" />
      </div>
    </div>
  );
}

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <CovenantCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Covenant card
// ---------------------------------------------------------------------------

interface CovenantCardProps {
  covenant: Covenant;
}

function CovenantCard({ covenant }: CovenantCardProps) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold">{covenant.name}</span>
              <Badge variant="outline" className="shrink-0 text-xs">
                {covenant.covenant_type_display}
              </Badge>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {covenant.member_count} {covenant.member_count === 1 ? 'member' : 'members'}
            </p>
            {covenant.sworn_objective && (
              <p className="mt-1 line-clamp-2 text-sm italic text-muted-foreground">
                {covenant.sworn_objective}
              </p>
            )}
          </div>
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <Link to={`/covenants/${covenant.id}`}>Detail</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function CovenantsListInner() {
  const { data, isLoading } = useCovenants();

  if (isLoading) return <LoadingSkeletons />;

  const covenants = data?.results ?? [];

  if (covenants.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="covenants-empty">
        You are not a member of any covenants.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="covenants-list">
      {covenants.map((covenant) => (
        <CovenantCard key={covenant.id} covenant={covenant} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function CovenantsListPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">Covenants</h1>
      <ErrorBoundary>
        <CovenantsListInner />
      </ErrorBoundary>
    </div>
  );
}
