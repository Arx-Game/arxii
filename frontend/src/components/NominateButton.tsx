/**
 * Nominate the writer of a pose or journal entry for good RP (#3738).
 *
 * Sits beside the reaction row. Pressed means this piece is one you cited
 * this week; pressing again withdraws it. It shows nothing about anyone
 * else: no count, no names, no budget. A nomination is invisible to the
 * nominee until the week settles, and this button is the nominator's only
 * trace of it besides the panel on the XP page.
 *
 * No self-guard of its own: the backend refuses your own characters through
 * any alt, and the mounting component (PoseUnit, the journal rows) decides
 * whether to show it at all.
 */

import { Award } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  useMyNominationsQuery,
  useNominateMutation,
  useWithdrawNominationMutation,
} from '@/progression/nominationQueries';
import type { NominationTargetType } from '@/progression/nominationQueries';

interface NominateButtonProps {
  targetType: NominationTargetType;
  targetId: number;
  /** The writer's name as shown on the piece, for the tooltip. */
  nomineeName: string;
}

export function NominateButton({ targetType, targetId, nomineeName }: NominateButtonProps) {
  const { data: nominations = [] } = useMyNominationsQuery();
  const nominateMutation = useNominateMutation();
  const withdrawMutation = useWithdrawNominationMutation();

  const existing = nominations.find(
    (row) => row.target_type === targetType && row.target_id === targetId
  );
  const cited = existing != null;
  const pending = nominateMutation.isPending || withdrawMutation.isPending;

  function handleClick() {
    if (pending) return;
    if (existing) {
      withdrawMutation.mutate(existing.id, {
        onError: (err: Error) => toast.error(err.message),
      });
    } else {
      nominateMutation.mutate(
        { targetType, targetId },
        { onError: (err: Error) => toast.error(err.message) }
      );
    }
  }

  const title = cited
    ? `Withdraw your nomination of ${nomineeName}`
    : `Nominate ${nomineeName} for good RP (they will not know who)`;

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7"
      onClick={handleClick}
      disabled={pending}
      title={title}
      aria-pressed={cited}
      data-testid="nominate-button"
    >
      <Award
        className={`h-4 w-4 ${cited ? 'fill-amber-400 text-amber-500' : 'text-muted-foreground'}`}
      />
    </Button>
  );
}
