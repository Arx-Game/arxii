/**
 * The nominator's own nominations this week (#3738), on the XP page.
 *
 * The one place a player sees their nominations listed: whom they nominated
 * and for which piece, with a way to take one back before the week settles.
 * Nothing here is about nominations received; those are invisible until the
 * settled XP appears in the transaction history.
 */
import { Award, X } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useMyNominationsQuery, useWithdrawNominationMutation } from '../nominationQueries';

const TARGET_TYPE_LABELS: Record<string, string> = {
  interaction: 'Pose',
  journal: 'Journal',
};

export function NominationsPanel() {
  const { data: nominations = [], isLoading } = useMyNominationsQuery();
  const withdrawMutation = useWithdrawNominationMutation();

  if (isLoading) return null;

  return (
    <Card data-testid="nominations-panel">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Award className="h-4 w-4" />
          Nominations this week
        </CardTitle>
      </CardHeader>
      <CardContent>
        {nominations.length > 0 ? (
          <ul className="space-y-2">
            {nominations.map((row) => (
              <li key={row.id} className="flex items-center justify-between text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs">
                    {TARGET_TYPE_LABELS[row.target_type] || row.target_type}
                  </span>
                  <span className="shrink-0 font-medium">{row.nominee_name}</span>
                  <span className="truncate text-muted-foreground">{row.target_name}</span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    withdrawMutation.mutate(row.id, {
                      onError: (err: Error) => toast.error(err.message),
                    })
                  }
                  disabled={withdrawMutation.isPending}
                  aria-label={`Withdraw nomination of ${row.nominee_name}`}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            Nobody nominated yet this week. Read a pose or a journal you liked and press the award
            beside it.
          </p>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          One nomination per person per week, however many pieces you cite. They never learn who; it
          settles into XP at the week&apos;s end.
        </p>
      </CardContent>
    </Card>
  );
}
