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

import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useOrganizationQuery,
  useHouseFeedQuery,
  useChooseCrisisOption,
  useStandingDeclarationsQuery,
} from '@/orgs/queries';
import { OperationsSection } from '@/tasking/components/OperationsSection';
import type { HouseCrisis, HouseDetail, HouseStature, StandingDeclaration } from '@/orgs/api';
import { DeclareStandingDialog } from '@/orgs/components/DeclareStandingDialog';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useOrganizationMembershipsQuery } from '@/reputation/queries';

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
        This organization&apos;s page is not yet public; full house and organization pages are
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

const TREND_ARROW: Record<string, string> = {
  rising: '↑',
  falling: '↓',
  steady: '→',
};

const STATURE_ROWS: Array<{ key: keyof HouseStature; label: string; hint: string }> = [
  { key: 'renown_strength', label: 'Renown', hint: 'The Gifted who stand with the house' },
  { key: 'military_strength', label: 'Military', hint: 'Banners and soldiery' },
  { key: 'economic_strength', label: 'Economy', hint: 'Coffers and income' },
  { key: 'allied_strength', label: 'Allies', hint: 'Strength sworn to your defense' },
];

/** The house's standing in the world (#3091): headline first, numbers below. */
function StatureCard({ stature }: { stature: HouseStature }) {
  return (
    <Card data-testid="stature-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <CardTitle className="text-lg">Stature</CardTitle>
          {stature.band_name && (
            <Badge variant={stature.trend === 'falling' ? 'destructive' : 'secondary'}>
              {stature.band_name} {TREND_ARROW[stature.trend] ?? ''}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {stature.headline && <p className="text-base italic">{stature.headline}</p>}
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold">{stature.perceived_total}</span>
          <span className="text-muted-foreground">as the world reckons it</span>
        </div>
        <ul className="space-y-1">
          {STATURE_ROWS.map(({ key, label, hint }) => (
            <li key={key} className="flex items-baseline justify-between">
              <span>
                {label} <span className="text-xs text-muted-foreground">{hint}</span>
              </span>
              <span className="font-mono">{stature[key] as number}</span>
            </li>
          ))}
          {stature.crisis_penalty > 0 && (
            <li className="flex items-baseline justify-between">
              <span>
                Threat drag{' '}
                <span className="text-xs text-muted-foreground">Open troubles weigh on you</span>
              </span>
              <span className="font-mono text-destructive">-{stature.crisis_penalty}</span>
            </li>
          )}
        </ul>
        <p className="text-muted-foreground">
          {stature.realm_rank != null && stature.realm_cohort_size != null && (
            <>
              {ordinal(stature.realm_rank)} of {stature.realm_cohort_size} polities of the realm
            </>
          )}
          {stature.prestige_rank != null && (
            <> · prestige rank {stature.prestige_rank} among all companies and houses</>
          )}
        </p>
      </CardContent>
    </Card>
  );
}

function ordinal(n: number): string {
  const rem10 = n % 10;
  const rem100 = n % 100;
  if (rem10 === 1 && rem100 !== 11) return `${n}st`;
  if (rem10 === 2 && rem100 !== 12) return `${n}nd`;
  if (rem10 === 3 && rem100 !== 13) return `${n}rd`;
  return `${n}th`;
}

function HouseSection({ orgId, house }: { orgId: number; house: HouseDetail }) {
  const { data: feed = [] } = useHouseFeedQuery(orgId, true);

  return (
    <div className="space-y-4">
      {house.stature && <StatureCard stature={house.stature} />}
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
                    <span className="text-muted-foreground">- {feature.description}</span>
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
                      {title.holder_name || (title.is_claimable ? 'vacant: claimable' : 'vacant')}
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
                  <span className="font-medium">{item.subject}</span>: {item.headline}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const DIRECTION_LABEL: Record<StandingDeclaration['direction'], string> = {
  favor: 'Favored',
  disfavor: 'Disfavored',
};

/** Standing/History panel (#3290): the org's public favor/disfavor record + a
 * declare affordance for the viewer's own persona, when its rank in this org
 * carries `can_declare_standing`. */
function StandingSection({ orgId, orgName }: { orgId: number; orgName: string }) {
  const { data: declarations = [], isLoading } = useStandingDeclarationsQuery(orgId);

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const { data: myMemberships = [] } = useOrganizationMembershipsQuery(true);
  const canDeclare = useMemo(
    () =>
      myMemberships.some(
        (m) => m.organization === orgId && m.rank?.can_declare_standing === true
      ),
    [myMemberships, orgId]
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Standing Declarations</CardTitle>
          {canDeclare && characterId !== null && (
            <DeclareStandingDialog
              organizationId={orgId}
              organizationName={orgName}
              characterId={characterId}
            >
              <Button size="sm" variant="outline">
                Declare Standing
              </Button>
            </DeclareStandingDialog>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-4 w-40" />
        ) : declarations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No standing has been declared.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {declarations.map((d) => (
              <li key={d.id} className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Badge variant={d.direction === 'favor' ? 'secondary' : 'destructive'}>
                    {DIRECTION_LABEL[d.direction]}
                  </Badge>
                  <span className="font-medium">{d.target_persona_name}</span>
                  <span className="text-muted-foreground">
                    by {d.declared_by_persona_name}
                  </span>
                </div>
                <p className="text-muted-foreground">{d.citation}</p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
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
      <StandingSection orgId={orgId} orgName={org.name} />
      <OperationsSection orgId={orgId} />
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
