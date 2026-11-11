/**
 * RoundThreadPull — a thread pull declared on its own for the round (#5066), through the
 * `combat_pull` registry action. It takes no action slot; the server allows one per round.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { ThreadPullDialog } from '@/magic/components/threads/ThreadPullDialog';
import { roundPullRequest } from '@/combat/dodging';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';

export interface RoundThreadPullProps {
  characterSheetId: number;
  encounterId: number;
  participantId: number;
  /** Every technique she can use this round; the server re-checks the pull. */
  techniqueIds: number[];
  /** The encounter's round: a successful pull hides the button until the next one. */
  roundNumber: number | null;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function RoundThreadPull({
  characterSheetId,
  encounterId,
  participantId,
  techniqueIds,
  roundNumber,
  isLocked,
  dispatchAction,
  onDispatched,
}: RoundThreadPullProps) {
  const [open, setOpen] = useState(false);
  const [pulledRound, setPulledRound] = useState<number | null | undefined>(undefined);

  if (pulledRound !== undefined && pulledRound === roundNumber) return null;

  return (
    <>
      <button
        type="button"
        data-testid="round-pull-btn"
        disabled={isLocked}
        onClick={() => setOpen(true)}
        className="rounded border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Pull threads for the round
      </button>
      <ThreadPullDialog
        characterSheetId={characterSheetId}
        open={open}
        onClose={() => setOpen(false)}
        combat={{
          encounterId,
          participantId,
          involvedTraitIds: [],
          involvedTechniqueIds: techniqueIds,
        }}
        onSelect={(selection) => {
          setOpen(false);
          dispatchAction(roundPullRequest(selection))
            .then((result) => {
              if (isDispatchFailure(result)) {
                toast.error(result.message ?? 'That pull was refused.');
                return;
              }
              if (result.message) toast.success(result.message);
              setPulledRound(roundNumber);
              onDispatched?.();
            })
            .catch((err: unknown) => {
              toast.error(err instanceof Error ? err.message : 'That pull was refused.');
            });
        }}
      />
    </>
  );
}
