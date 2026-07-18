/**
 * ReclamationPage (#2368) — stolen-property claims: file at discovery, work the
 * trace hop by hop, then choose the recovery route (lawful seizure vs steal-back).
 *
 * Self-only surface; the current holder is never notified a claim exists.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  advanceTrace,
  fetchClaimable,
  fetchMyClaims,
  fileClaim,
  reportClaim,
  takeBack,
  type ReclamationClaimRow,
} from '@/reclamation/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const OPEN_STATUS = 'open';

function ClaimCard({ claim }: { claim: ReclamationClaimRow }) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['reclamation'] }).catch(() => {});
  };
  const advance = useMutation({ mutationFn: () => advanceTrace(claim.id), onSuccess: invalidate });
  const report = useMutation({ mutationFn: () => reportClaim(claim.id), onSuccess: invalidate });
  const steal = useMutation({ mutationFn: () => takeBack(claim.id), onSuccess: invalidate });
  const isOpen = claim.status === OPEN_STATUS;

  return (
    <Card data-testid="claim-card">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>{claim.item_name}</span>
          <span className="text-xs font-normal uppercase text-muted-foreground">
            {claim.status}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {claim.steps.length > 0 && (
          <ol className="space-y-1 text-sm text-muted-foreground">
            {claim.steps.map((step) => (
              <li key={step.position}>
                {step.position}. {step.revealed_text}
              </li>
            ))}
          </ol>
        )}
        {isOpen && !claim.trace_complete && (
          <p className="text-sm text-muted-foreground">
            The trail continues — someone knows where it went next.
          </p>
        )}
        {isOpen && claim.trace_complete && (
          <p className="text-sm font-medium">
            You know where it is. How you get it back is up to you.
          </p>
        )}
        {isOpen && (
          <div className="flex flex-wrap gap-2">
            {!claim.trace_complete && (
              <Button
                size="sm"
                variant="outline"
                disabled={advance.isPending}
                onClick={() => advance.mutate()}
                title="Work your contacts for the next link in the chain. A botched attempt chills the trail for a while."
              >
                Follow the trail
              </Button>
            )}
            {claim.trace_complete && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={report.isPending}
                  onClick={() => report.mutate()}
                  title="Put it before the authorities: a lawful seizure through the justice system."
                >
                  Report to the authorities
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={steal.isPending}
                  onClick={() => steal.mutate()}
                  title="Take it back yourself. Recovering your own property is not a crime — getting caught doing it may complicate things."
                >
                  Steal it back
                </Button>
              </>
            )}
          </div>
        )}
        {(advance.isError || report.isError || steal.isError) && (
          <p className="text-sm text-destructive">
            {[advance.error, report.error, steal.error]
              .filter((e): e is Error => e instanceof Error)
              .map((e) => e.message)
              .join(' ')}
          </p>
        )}
        {advance.data?.chilled && (
          <p className="text-sm text-muted-foreground">
            Your inquiry spooked the trail — it has gone cold for now. Try again later.
          </p>
        )}
        {report.data?.reported && (
          <p className="text-sm text-muted-foreground">
            The report is filed — the holder now carries the receiving-stolen-goods risk.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ReclamationPage() {
  const qc = useQueryClient();
  const { data: claims = [], isLoading: claimsLoading } = useQuery({
    queryKey: ['reclamation', 'claims'],
    queryFn: fetchMyClaims,
  });
  const { data: claimable = [], isLoading: claimableLoading } = useQuery({
    queryKey: ['reclamation', 'claimable'],
    queryFn: fetchClaimable,
  });
  const file = useMutation({
    mutationFn: fileClaim,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reclamation'] }).catch(() => {});
    },
  });

  if (claimsLoading || claimableLoading) {
    return <p className="p-8 text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="container mx-auto max-w-3xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Stolen Property</h1>

      {claimable.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Stolen from you</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {claimable.map((row) => (
              <div
                key={row.item}
                className="flex items-center justify-between text-sm"
                data-testid="claimable-row"
              >
                <span>{row.item_name}</span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={file.isPending}
                  onClick={() => file.mutate(row.item)}
                  title="Report the theft and open a trace on where it went."
                >
                  File claim
                </Button>
              </div>
            ))}
            {file.isError && file.error instanceof Error && (
              <p className="text-sm text-destructive">{file.error.message}</p>
            )}
          </CardContent>
        </Card>
      )}

      {claims.length === 0 && claimable.length === 0 ? (
        <p className="text-muted-foreground" data-testid="reclamation-empty">
          Nothing of yours is missing, so far as you know.
        </p>
      ) : (
        claims.map((claim) => <ClaimCard key={claim.id} claim={claim} />)
      )}
    </div>
  );
}
