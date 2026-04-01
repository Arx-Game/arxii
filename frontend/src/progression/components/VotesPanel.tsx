import { Heart, X } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useMyVotesQuery, useRemoveVoteMutation, useVoteBudgetQuery } from '../voteQueries';

const TARGET_TYPE_LABELS: Record<string, string> = {
  interaction: 'Pose',
  scene_participation: 'Scene',
  journal: 'Journal',
};

export function VotesPanel() {
  const { data: votes = [], isLoading } = useMyVotesQuery();
  const { data: budget } = useVoteBudgetQuery();
  const removeMutation = useRemoveVoteMutation();

  if (isLoading) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Heart className="h-4 w-4" />
            Votes
          </CardTitle>
          {budget && (
            <span className="text-sm text-muted-foreground">
              {budget.votes_remaining} of {budget.base_votes + budget.scene_bonus_votes} remaining
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {votes.length > 0 ? (
          <ul className="space-y-2">
            {votes.map((vote) => (
              <li key={vote.id} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs">
                    {TARGET_TYPE_LABELS[vote.target_type] || vote.target_type}
                  </span>
                  <span className="truncate">{vote.target_name}</span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    removeMutation.mutate(vote.id, {
                      onError: (err: Error) => toast.error(err.message),
                    })
                  }
                  disabled={removeMutation.isPending}
                  aria-label={`Remove vote for ${vote.target_name}`}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-center text-sm text-muted-foreground">No votes cast this week</p>
        )}
      </CardContent>
    </Card>
  );
}
