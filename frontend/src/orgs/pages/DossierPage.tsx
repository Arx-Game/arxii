/**
 * DossierPage — the match-review dossier (#2999).
 *
 * Readable by ANY authenticated player (the org page proper stays
 * members-only): weighing a match means reviewing rival houses. Shows the
 * candidate's public standing, standing instruments, known troubles (covert
 * ones only when YOUR org has paid spycraft to know), recent shifts, and
 * consort capacity for its title holders.
 *
 * Route: /orgs/:id/dossier
 */

import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchOrgDossier, type OrgDossier } from '@/orgs/api';

const TREND_ARROW: Record<string, string> = {
  rising: '↑',
  falling: '↓',
  steady: '→',
};

function DossierInner({ orgId }: { orgId: number }) {
  const { data, isLoading, isError } = useQuery<OrgDossier>({
    queryKey: ['orgs', 'dossier', orgId],
    queryFn: () => fetchOrgDossier(orgId),
  });

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No dossier could be assembled for this house.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="dossier-page">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-xl">{data.name}</CardTitle>
            {data.org_type_name && <Badge variant="outline">{data.org_type_name}</Badge>}
            {data.band_name && (
              <Badge variant={data.trend === 'falling' ? 'destructive' : 'secondary'}>
                {data.band_name} {TREND_ARROW[data.trend] ?? ''}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {data.headline && <p className="text-base italic">{data.headline}</p>}
          {data.perceived_total != null && (
            <p>
              <span className="text-3xl font-semibold">{data.perceived_total}</span>{' '}
              <span className="text-muted-foreground">as the world reckons it</span>
            </p>
          )}
          <p className="text-muted-foreground">
            {data.realm_rank != null && data.realm_cohort_size != null && (
              <>
                Rank {data.realm_rank} of {data.realm_cohort_size} polities of the realm
              </>
            )}
            {data.prestige_rank != null && <> · prestige rank {data.prestige_rank}</>}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Standing Instruments</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {data.pacts.length === 0 && data.betrothals.length === 0 ? (
            <p className="text-muted-foreground">No pacts stand. They face the dark alone.</p>
          ) : (
            <ul className="space-y-1">
              {data.pacts.map((pact, index) => (
                <li key={index} className="flex items-baseline justify-between">
                  <span>
                    <Badge variant="secondary" className="mr-2">
                      {pact.kind}
                    </Badge>
                    with {pact.counterpart}
                  </span>
                  <span className="text-muted-foreground">{pact.commitments.join(', ')}</span>
                </li>
              ))}
              {data.betrothals.map((vow, index) => (
                <li key={`vow-${index}`}>
                  <Badge variant="outline" className="mr-2">
                    Betrothal
                  </Badge>
                  {vow}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Known Troubles</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {data.open_crises.length === 0 ? (
            <p className="text-muted-foreground">No troubles known. Spies might know better.</p>
          ) : (
            <ul className="space-y-1">
              {data.open_crises.map((crisis, index) => (
                <li key={index} className="flex items-baseline justify-between">
                  <span>
                    <Badge variant="destructive" className="mr-2">
                      {crisis.severity}
                    </Badge>
                    {crisis.type_name || 'Crisis'}
                    {crisis.domain_name && <> in {crisis.domain_name}</>}
                  </span>
                  {crisis.known_covertly && (
                    <span className="text-xs italic text-muted-foreground">
                      known through your spies
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {data.consorts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Consort Capacity</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <ul className="space-y-1">
              {data.consorts.map((row, index) => (
                <li key={index} className="flex items-baseline justify-between">
                  <span>{row.holder}</span>
                  <span className="text-muted-foreground">
                    {row.consorts}
                    {row.cap != null ? ` of ${row.cap}` : ''} consorts
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Recent Turns of Fortune</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {data.recent_shifts.length === 0 ? (
            <p className="text-muted-foreground">Their fortunes hold steady.</p>
          ) : (
            <ul className="space-y-1">
              {data.recent_shifts.map((shift, index) => (
                <li key={index} className="flex items-baseline justify-between">
                  <span>
                    {shift.cause}
                    {shift.subject && (
                      <span className="text-muted-foreground"> — {shift.subject}</span>
                    )}
                  </span>
                  <span
                    className={`font-mono ${shift.delta_perceived < 0 ? 'text-destructive' : ''}`}
                  >
                    {shift.delta_perceived > 0 ? '+' : ''}
                    {shift.delta_perceived}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function DossierPage() {
  const { id = '' } = useParams<{ id: string }>();
  const orgId = parseInt(id, 10);

  if (isNaN(orgId) || orgId <= 0) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No such house.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <DossierInner orgId={orgId} />
      </ErrorBoundary>
    </div>
  );
}
