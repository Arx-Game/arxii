/**
 * OrgPage — organization detail page (#1446, house layer #1884).
 *
 * A click-through destination for organization links elsewhere in the app
 * (e.g. a character's family name on the sheet). Family-rooted orgs render
 * the house block on top of the base metadata: fealty, titles, domains, and
 * the house feed (the Arx 1 informs replacement). Anyone who isn't an active
 * member (or an org that doesn't exist) sees a placeholder.
 *
 * Route: /orgs/:id
 */

import { useParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOrganizationQuery, useHouseFeedQuery } from '@/orgs/queries';
import type { HouseDetail } from '@/orgs/api';

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

function HouseSection({ orgId, house }: { orgId: number; house: HouseDetail }) {
  const { data: feed = [] } = useHouseFeedQuery(orgId, true);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">House of {house.family_name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {house.liege_name && (
            <p>
              <span className="text-muted-foreground">Sworn to</span> {house.liege_name}
            </p>
          )}
          {house.vassal_names.length > 0 && (
            <p>
              <span className="text-muted-foreground">Vassals:</span>{' '}
              {house.vassal_names.join(', ')}
            </p>
          )}
          {house.titles.length > 0 && (
            <div>
              <h3 className="mb-1 font-semibold">Titles</h3>
              <ul className="space-y-1">
                {house.titles.map((title) => (
                  <li key={title.id} className="flex items-baseline justify-between">
                    <span>
                      {title.name}
                      <Badge variant="outline" className="ml-2 text-xs">
                        {title.tier}
                      </Badge>
                    </span>
                    <span className="text-muted-foreground">
                      {title.holder_name || (title.is_claimable ? 'vacant — claimable' : 'vacant')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {house.domains.length > 0 && (
            <div>
              <h3 className="mb-1 font-semibold">Domains</h3>
              <ul className="space-y-1">
                {house.domains.map((domain) => (
                  <li key={domain.name} className="flex items-baseline justify-between">
                    <span>{domain.name}</span>
                    <span className="text-muted-foreground">
                      pop {domain.population} · prosperity {domain.prosperity} · unrest{' '}
                      {domain.unrest}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">House Tidings</CardTitle>
        </CardHeader>
        <CardContent>
          {feed.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing stirring.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {feed.map((item, index) => (
                <li key={index}>
                  <Badge variant={item.kind === 'scandal' ? 'destructive' : 'secondary'}>
                    {item.kind}
                  </Badge>{' '}
                  <span className="font-medium">{item.subject}</span> — {item.headline}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function OrgPageInner({ orgId }: { orgId: number }) {
  const { data: org, isLoading, isError } = useOrganizationQuery(orgId);

  if (isLoading) return <OrgSkeleton />;

  if (isError || !org) {
    return <NotYetPublicCard />;
  }

  return (
    <div className="space-y-4">
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
      {org.house && <HouseSection orgId={orgId} house={org.house} />}
    </div>
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
