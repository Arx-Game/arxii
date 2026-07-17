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
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOrganizationQuery, useHouseFeedQuery, useChooseCrisisOption } from '@/orgs/queries';
import type { HouseCrisis, HouseDetail } from '@/orgs/api';

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

const SEVERITY_LABEL: Record<string, string> = {
  trouble: 'Trouble',
  crisis: 'Crisis',
  catastrophe: 'Catastrophe',
};

const OPTION_LABEL: Record<string, string> = {
  pay: 'Pay it off',
  mission: 'Confront it',
  wait: 'Ride it out',
};

/** An open domain crisis awaiting the house's judgment call (#2238). */
function CrisisCard({ orgId, crisis }: { orgId: number; crisis: HouseCrisis }) {
  const mutation = useChooseCrisisOption(orgId);

  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
      <div className="flex items-center gap-2">
        <Badge variant="destructive">{SEVERITY_LABEL[crisis.severity] ?? crisis.severity}</Badge>
        <span className="font-semibold">
          {crisis.type_name || 'Crisis'} in {crisis.domain_name}
        </span>
      </div>
      {crisis.description && (
        <p className="mt-1 text-sm text-muted-foreground">{crisis.description}</p>
      )}
      {crisis.chosen_kind ? (
        <p className="mt-2 text-sm italic text-muted-foreground">
          Course chosen: {OPTION_LABEL[crisis.chosen_kind] ?? crisis.chosen_kind}
        </p>
      ) : (
        crisis.options.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {crisis.options.map((option) => (
              <Button
                key={option.id}
                size="sm"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ crisisId: crisis.id, optionId: option.id })}
              >
                {OPTION_LABEL[option.kind] ?? option.kind}
                {option.kind === 'pay' ? ` (${option.cost_coppers}c)` : ''}
              </Button>
            ))}
          </div>
        )
      )}
      {mutation.isError && (
        <p className="mt-2 text-sm text-destructive">
          {mutation.error instanceof Error ? mutation.error.message : 'That action failed.'}
        </p>
      )}
    </div>
  );
}

function HouseSection({ orgId, house }: { orgId: number; house: HouseDetail }) {
  const { data: feed = [] } = useHouseFeedQuery(orgId, true);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">House of {house.family_name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {house.open_crises.length > 0 && (
            <div className="space-y-2">
              {house.open_crises.map((crisis) => (
                <CrisisCard key={crisis.id} orgId={orgId} crisis={crisis} />
              ))}
            </div>
          )}
          {house.aspects.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {house.aspects.map((aspect) => (
                <Badge
                  key={`${aspect.definition}-${aspect.option}`}
                  variant="secondary"
                  title={aspect.description}
                >
                  {aspect.definition}: {aspect.option}
                </Badge>
              ))}
            </div>
          )}
          {house.features.length > 0 && (
            <div>
              <h3 className="mb-1 font-semibold">Ways of the House</h3>
              <ul className="space-y-1">
                {house.features.map((feature) => (
                  <li key={feature.slug}>
                    <span className="font-medium">{feature.name}</span>{' '}
                    <span className="text-muted-foreground">— {feature.description}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
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
          {org.words && <p className="text-sm italic">&ldquo;{org.words}&rdquo;</p>}
          {org.colors && (
            <p className="text-sm">
              <span className="text-muted-foreground">Colors:</span> {org.colors}
            </p>
          )}
          {org.sigil_description && (
            <p className="text-sm">
              <span className="text-muted-foreground">Sigil:</span> {org.sigil_description}
            </p>
          )}
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
