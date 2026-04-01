/**
 * Compact vote toggle button for inline use next to interactions, scene participations, or journals.
 * Shows a filled heart when voted and an outline heart when not.
 */

import { Heart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  useMyVotesQuery,
  useVoteBudgetQuery,
  useCastVoteMutation,
  useRemoveVoteMutation,
} from '@/progression/voteQueries';
import type { VoteTargetType } from '@/progression/voteQueries';

interface VoteButtonProps {
  targetType: VoteTargetType;
  targetId: number;
}

export function VoteButton({ targetType, targetId }: VoteButtonProps) {
  const { data: votes = [] } = useMyVotesQuery();
  const { data: budget } = useVoteBudgetQuery();
  const castVote = useCastVoteMutation();
  const removeVote = useRemoveVoteMutation();

  const existingVote = votes.find((v) => v.target_type === targetType && v.target_id === targetId);
  const isVoted = !!existingVote;
  const votesRemaining = budget?.votes_remaining ?? 0;
  const isDisabled =
    (!isVoted && votesRemaining <= 0) || castVote.isPending || removeVote.isPending;

  function handleClick() {
    if (castVote.isPending || removeVote.isPending) return;
    if (isVoted && existingVote) {
      removeVote.mutate(existingVote.id);
    } else {
      castVote.mutate({ targetType, targetId });
    }
  }

  const tooltipText = isVoted
    ? 'Remove vote'
    : votesRemaining > 0
      ? `Vote (${votesRemaining} remaining)`
      : 'No votes remaining';

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative h-7 w-7"
      onClick={handleClick}
      disabled={isDisabled}
      title={tooltipText}
    >
      <Heart
        className={`h-4 w-4 ${isVoted ? 'fill-red-500 text-red-500' : 'text-muted-foreground'}`}
      />
      {budget != null && !isVoted && votesRemaining > 0 && (
        <span className="absolute -right-1 -top-1 text-[10px] font-medium leading-none text-muted-foreground">
          {votesRemaining}
        </span>
      )}
    </Button>
  );
}
