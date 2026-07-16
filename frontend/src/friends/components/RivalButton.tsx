import { useDeclareRivalMutation, useRivalsQuery, useWithdrawRivalMutation } from '../queries';

/** "Declare this character a rival" — shown on another character's sheet/card (#2170).
 *
 * Rivalry is **double opt-in**: your declaration is one side's intent, and the rivalry (and the
 * RIVALS consent mode) only takes effect once they declare you back. A one-way declaration is
 * just you nursing a grudge. `viewerEntryId` is your active RosterEntry; `targetEntryId` is the
 * viewed character's RosterEntry.
 */
export function RivalButton({
  viewerEntryId,
  targetEntryId,
  targetName,
}: {
  viewerEntryId: number | null;
  targetEntryId: number;
  targetName: string;
}) {
  const { data } = useRivalsQuery();
  const declare = useDeclareRivalMutation();
  const withdraw = useWithdrawRivalMutation();

  if (viewerEntryId === null) return null;

  const existing = (data?.results ?? []).find(
    (row) => row.rivaler_entry === viewerEntryId && row.rival_entry === targetEntryId
  );

  if (existing) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm italic text-muted-foreground">
          {existing.is_mutual
            ? `You and ${targetName} are mutual rivals.`
            : `Rival declared — mutual once ${targetName} declares you back.`}
        </span>
        <button
          type="button"
          disabled={withdraw.isPending}
          className="rounded border px-3 py-1 text-sm hover:bg-accent disabled:opacity-50"
          onClick={() => withdraw.mutate(existing.id)}
        >
          Withdraw
        </button>
        {withdraw.isError && (
          <span className="text-sm text-destructive">{(withdraw.error as Error).message}</span>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={declare.isPending}
        title="Double opt-in: the rivalry only takes effect once they declare you back."
        className="rounded border px-3 py-1 text-sm hover:bg-accent disabled:opacity-50"
        onClick={() => declare.mutate({ viewer: viewerEntryId, rival: targetEntryId })}
      >
        ⚔ Declare rival
      </button>
      {declare.isError && (
        <span className="text-sm text-destructive">{(declare.error as Error).message}</span>
      )}
    </div>
  );
}
