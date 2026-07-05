/**
 * OrgPage — stub organization detail page (#1446).
 *
 * This is a click-through destination for organization links elsewhere in the
 * app (e.g. a character's family name on the sheet). It is explicitly NOT the
 * full org/house page — that design lives in #1884. For now it shows the org
 * name and the light metadata the members-only serializer exposes; anyone who
 * isn't an active member (or an org that doesn't exist) sees a placeholder.
 *
 * Route: /orgs/:id
 */

import { useParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOrganizationQuery } from '@/orgs/queries';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function OrgSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-40" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Not-yet-public placeholder — covers both non-member (query error) and
// missing/empty organization results.
// ---------------------------------------------------------------------------

function NotYetPublicCard() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        This organization&apos;s page is not yet public — full house and organization pages are
        coming (#1884).
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Inner page
// ---------------------------------------------------------------------------

export function OrgPageInner({ orgId }: { orgId: number }) {
  const { data: org, isLoading, isError } = useOrganizationQuery(orgId);

  if (isLoading) return <OrgSkeleton />;

  if (isError || !org) {
    return <NotYetPublicCard />;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <CardTitle className="text-xl">{org.name}</CardTitle>
          <Badge variant="outline">{org.org_type_name}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-muted-foreground">{org.society_name}</p>
        {org.description && <p className="text-sm">{org.description}</p>}
        {org.ranks.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-2">
            {org.ranks.map((rank) => (
              <Badge key={rank.id} variant="secondary" className="text-xs">
                {rank.name}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function OrgPage() {
  const { id = '' } = useParams<{ id: string }>();
  const orgId = parseInt(id, 10);

  if (isNaN(orgId) || orgId <= 0) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <NotYetPublicCard />
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <OrgPageInner orgId={orgId} />
      </ErrorBoundary>
    </div>
  );
}
